import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.models import OrganizationMembership, User
from app.schemas.common import TokenResponse, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    organization_id: uuid.UUID | None = None


class SwitchOrgRequest(BaseModel):
    organization_id: uuid.UUID


@router.post("/token", response_model=TokenResponse)
@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == req.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    role: str | None = None
    target_org_id = req.organization_id

    # If org is specified or pick the first active org
    if target_org_id:
        mem_res = await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.organization_id == target_org_id,
                OrganizationMembership.is_active == True,
            )
        )
        membership = mem_res.scalar_one_or_none()
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not an active member of this organization",
            )
        role = membership.role.value
    else:
        mem_res = await db.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.is_active == True,
            )
        )
        membership = mem_res.scalars().first()
        if membership:
            target_org_id = membership.organization_id
            role = membership.role.value

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "org_id": str(target_org_id) if target_org_id else None,
        "role": role,
    }
    access_token = create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserInfo.model_validate(user),
        current_org_id=target_org_id,
        role=role,
    )


@router.get("/me")
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    mem_res = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.is_active == True,
        )
    )
    memberships = mem_res.scalars().all()

    return {
        "user": UserInfo.model_validate(current_user),
        "memberships": [
            {
                "id": str(m.id),
                "organization_id": str(m.organization_id),
                "role": m.role.value,
                "hourly_rate": float(m.hourly_rate) if m.hourly_rate else None,
                "skills": m.skills or [],
            }
            for m in memberships
        ],
    }


@router.post("/switch-org", response_model=TokenResponse)
async def switch_organization(
    req: SwitchOrgRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    mem_res = await db.execute(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.organization_id == req.organization_id,
            OrganizationMembership.is_active == True,
        )
    )
    membership = mem_res.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an active member of this organization",
        )

    token_data = {
        "sub": str(current_user.id),
        "email": current_user.email,
        "org_id": str(membership.organization_id),
        "role": membership.role.value,
    }
    access_token = create_access_token(token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserInfo.model_validate(current_user),
        current_org_id=membership.organization_id,
        role=membership.role.value,
    )


@router.post("/logout")
async def logout(current_user: Annotated[User, Depends(get_current_user)]) -> dict:
    return {"message": "Logged out successfully"}
