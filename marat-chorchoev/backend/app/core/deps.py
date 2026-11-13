"""Authentication and organization context for protected endpoints.

The bearer token identifies the *user*. The ``X-Organization-ID`` header selects the
organization and is checked against the user's memberships on every request (AUTH-03).
"""

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BadRequest, Forbidden, Unauthorized
from app.core.security import hash_token
from app.database import get_db
from app.models.base import utcnow
from app.models.models import AuthSession, Organization, OrganizationMembership, Role, User

DB = Annotated[AsyncSession, Depends(get_db)]


@dataclass(slots=True)
class Ctx:
    """Everything an endpoint needs to authorize a request."""

    user: User
    membership: OrganizationMembership
    org: Organization
    session_id: uuid.UUID

    @property
    def org_id(self) -> uuid.UUID:
        return self.org.id

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def is_staff(self) -> bool:
        return self.membership.role in (Role.ADMIN, Role.DISPATCHER)

    @property
    def is_admin(self) -> bool:
        return self.membership.role == Role.ADMIN

    @property
    def is_requester(self) -> bool:
        return self.membership.role == Role.REQUESTER

    @property
    def is_technician(self) -> bool:
        return self.membership.role == Role.TECHNICIAN


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    return token.strip()


async def authenticate(db: AsyncSession, token: str) -> tuple[User, AuthSession]:
    row = (
        await db.execute(
            select(User, AuthSession)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(AuthSession.token_hash == hash_token(token))
        )
    ).first()
    if row is None:
        raise Unauthorized("Session is not valid. Sign in again.", code="SESSION_INVALID")
    user, session = row
    if session.revoked_at is not None:
        raise Unauthorized("Session was signed out. Sign in again.", code="SESSION_REVOKED")
    if session.expires_at <= utcnow():
        raise Unauthorized("Session expired. Sign in again.", code="SESSION_EXPIRED")
    if not user.is_active:
        raise Unauthorized("This account is deactivated.", code="ACCOUNT_DEACTIVATED")
    return user, session


async def resolve_membership(
    db: AsyncSession, user: User, org_header: str | None
) -> tuple[OrganizationMembership, Organization]:
    if not org_header:
        raise BadRequest("X-Organization-ID header is required.", code="ORGANIZATION_REQUIRED")
    try:
        org_id = uuid.UUID(org_header)
    except ValueError as exc:
        raise BadRequest(
            "X-Organization-ID is not a valid id.", code="ORGANIZATION_INVALID"
        ) from exc
    row = (
        await db.execute(
            select(OrganizationMembership, Organization)
            .join(Organization, Organization.id == OrganizationMembership.org_id)
            .where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.org_id == org_id,
            )
        )
    ).first()
    # Same answer whether the organization does not exist or the user is not in it.
    if row is None:
        raise Forbidden("You are not a member of this organization.", code="NOT_A_MEMBER")
    membership, org = row
    if not membership.is_active or not org.is_active:
        raise Forbidden(
            "Your access to this organization is deactivated.", code="MEMBERSHIP_DEACTIVATED"
        )
    return membership, org


async def get_current_user(request: Request, db: DB) -> tuple[User, AuthSession]:
    return await authenticate(db, bearer_token(request))


async def get_ctx(
    auth: Annotated[tuple[User, AuthSession], Depends(get_current_user)],
    db: DB,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> Ctx:
    user, session = auth
    membership, org = await resolve_membership(db, user, x_organization_id)
    return Ctx(user=user, membership=membership, org=org, session_id=session.id)


CurrentCtx = Annotated[Ctx, Depends(get_ctx)]


def require(*roles: Role) -> Callable[..., Coroutine[Any, Any, Ctx]]:
    async def checker(ctx: CurrentCtx) -> Ctx:
        if ctx.membership.role not in roles:
            raise Forbidden("Your role does not allow this action.", code="ROLE_FORBIDDEN")
        return ctx

    return checker


StaffCtx = Annotated[Ctx, Depends(require(Role.ADMIN, Role.DISPATCHER))]
AdminCtx = Annotated[Ctx, Depends(require(Role.ADMIN))]
TechnicianCtx = Annotated[Ctx, Depends(require(Role.TECHNICIAN))]
RequesterCtx = Annotated[Ctx, Depends(require(Role.REQUESTER))]
