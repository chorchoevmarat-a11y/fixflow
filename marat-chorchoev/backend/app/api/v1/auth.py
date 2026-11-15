from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body
from app.config import settings
from app.core.deps import DB, get_current_user, resolve_membership
from app.core.errors import Forbidden, TooManyRequests, Unauthorized
from app.core.security import hash_password, hash_token, new_session_token, verify_password
from app.models.base import utcnow
from app.models.models import (
    AuthSession,
    LoginAttempt,
    Organization,
    OrganizationMembership,
    Role,
    TechnicianProfile,
    User,
)
from app.services.common import audit, iso

router = APIRouter(prefix="/auth", tags=["auth"])

__all__ = ["hash_password", "router"]


class LoginBody(Body):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


async def _memberships(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    rows = await db.execute(
        select(OrganizationMembership, Organization, TechnicianProfile.id)
        .join(Organization, Organization.id == OrganizationMembership.org_id)
        .outerjoin(TechnicianProfile, TechnicianProfile.membership_id == OrganizationMembership.id)
        .where(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
        .order_by(Organization.name)
    )
    return [
        {
            "membership_id": str(membership.id),
            "organization_id": str(org.id),
            "organization_name": org.name,
            "timezone": org.timezone,
            "currency": org.currency,
            "role": membership.role,
            "technician_id": str(tech_id)
            if tech_id and membership.role == Role.TECHNICIAN
            else None,
        }
        for membership, org, tech_id in rows
    ]


def _user(user: User) -> dict[str, Any]:
    return {"id": str(user.id), "email": user.email, "full_name": user.full_name}


async def _security_event(db: AsyncSession, user: User, action: str, summary: str) -> None:
    """Write the event into the audit trail of every organization the user belongs to."""
    org_ids = await db.scalars(
        select(OrganizationMembership.org_id).where(OrganizationMembership.user_id == user.id)
    )
    for org_id in org_ids:
        audit(
            db,
            org_id=org_id,
            actor_id=user.id,
            action=action,
            target_type="user",
            target_id=user.id,
            summary=summary,
            is_public=False,
        )


@router.post(
    "/login",
    summary="Sign in with email and password",
    responses={401: {"description": "Invalid credentials"}, 429: {"description": "Rate limited"}},
)
async def login(body: LoginBody, request: Request, db: DB) -> dict[str, Any]:
    email = body.email.lower()
    ip = request.client.host if request.client else None
    now = utcnow()
    window_start = now - timedelta(minutes=settings.LOGIN_FAILURE_WINDOW_MINUTES)

    last_success = await db.scalar(
        select(func.max(LoginAttempt.created_at)).where(
            LoginAttempt.email == email, LoginAttempt.succeeded.is_(True)
        )
    )
    since = max(window_start, last_success) if last_success else window_start
    failures = await db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.email == email,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.created_at > since,
        )
    )
    ip_failures = 0
    if ip is not None:
        ip_failures = await db.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(
                LoginAttempt.ip_address == ip,
                LoginAttempt.succeeded.is_(False),
                LoginAttempt.created_at > window_start,
            )
        )
    if (failures or 0) >= settings.LOGIN_MAX_FAILURES or (
        ip_failures or 0
    ) >= settings.LOGIN_MAX_FAILURES * 10:
        raise TooManyRequests(
            "Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(settings.LOGIN_FAILURE_WINDOW_MINUTES * 60)},
        )

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not password_ok:
        db.add(LoginAttempt(email=email, ip_address=ip, succeeded=False))
        if user is not None:
            await _security_event(
                db, user, "auth.login_failed", f"Failed sign-in attempt for {email}"
            )
        await db.commit()
        raise Unauthorized("Email or password is incorrect.", code="INVALID_CREDENTIALS")

    memberships = await _memberships(db, user)
    if not user.is_active or not memberships:
        # ROLE-05: deactivated accounts cannot create sessions.
        await _security_event(
            db, user, "auth.login_denied", f"Sign-in denied for deactivated account {email}"
        )
        await db.commit()
        raise Forbidden("This account is deactivated.", code="ACCOUNT_DEACTIVATED")

    token = new_session_token()
    expires_at = now + timedelta(minutes=settings.SESSION_TTL_MINUTES)
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token), expires_at=expires_at))
    db.add(LoginAttempt(email=email, ip_address=ip, succeeded=True))
    await db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": iso(expires_at),
        "user": _user(user),
        "memberships": memberships,
    }


@router.post("/logout", summary="Sign out and revoke the current session")
async def logout(
    auth: Annotated[tuple[User, AuthSession], Depends(get_current_user)], db: DB
) -> dict[str, str]:
    user, session = auth
    session.revoked_at = utcnow()
    await _security_event(db, user, "auth.session_revoked", f"{user.email} signed out")
    await db.commit()
    return {"status": "signed_out"}


@router.get("/me", summary="Current user, memberships, and the selected membership")
async def me(
    auth: Annotated[tuple[User, AuthSession], Depends(get_current_user)],
    db: DB,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    user, session = auth
    memberships = await _memberships(db, user)
    current = None
    if x_organization_id:
        membership, _ = await resolve_membership(db, user, x_organization_id)
        current = next((m for m in memberships if m["membership_id"] == str(membership.id)), None)
    return {
        "user": _user(user),
        "memberships": memberships,
        "current_membership": current,
        "session_expires_at": iso(session.expires_at),
    }
