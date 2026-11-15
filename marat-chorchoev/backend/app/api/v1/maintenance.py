"""Preventive maintenance plans and generation (PM-01..05)."""

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body
from app.core.deps import DB, Ctx, StaffCtx
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models.models import (
    Asset,
    AssetStatus,
    MaintenancePlan,
    Priority,
    Recurrence,
    ServiceCategory,
    ServiceRequest,
)
from app.services import idempotency
from app.services.common import PageDep, audit, count_rows, iso, page_body, request_ref
from app.services.idempotency import IdempotencyHeader
from app.services.maintenance import generate, next_occurrence

router = APIRouter(prefix="/maintenance-plans", tags=["maintenance"])


class PlanCreate(Body):
    asset_id: uuid.UUID
    category_id: uuid.UUID
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=20, max_length=3000)
    priority: Priority = Priority.NORMAL
    first_date: date
    recurrence: Recurrence


class PlanPatch(Body):
    title: str | None = Field(default=None, min_length=5, max_length=120)
    description: str | None = Field(default=None, min_length=20, max_length=3000)
    priority: Priority | None = None
    is_enabled: bool | None = None


class GenerateBody(Body):
    as_of: date = Field(description="Generate every occurrence due on or before this date")
    plan_id: uuid.UUID | None = None


async def _view(db: AsyncSession, plan: MaintenancePlan, asset: Asset, category_name: str) -> dict:
    generated = await db.scalar(
        select(func.count())
        .select_from(ServiceRequest)
        .where(ServiceRequest.maintenance_plan_id == plan.id)
    )
    upcoming = await next_occurrence(db, plan) if asset.status == AssetStatus.ACTIVE else None
    return {
        "id": str(plan.id),
        "title": plan.title,
        "description": plan.description,
        "priority": plan.priority,
        "first_date": plan.first_date.isoformat(),
        "recurrence": plan.recurrence,
        "is_enabled": plan.is_enabled,
        "asset": {
            "id": str(asset.id),
            "code": asset.code,
            "name": asset.name,
            "status": asset.status,
        },
        "category": {"id": str(plan.category_id), "name": category_name},
        "next_occurrence": upcoming.isoformat() if upcoming else None,
        "generated_count": generated or 0,
        "created_at": iso(plan.created_at),
    }


def _query(ctx: Ctx) -> Any:
    return (
        select(MaintenancePlan, Asset, ServiceCategory.name)
        .join(Asset, Asset.id == MaintenancePlan.asset_id)
        .join(ServiceCategory, ServiceCategory.id == MaintenancePlan.category_id)
        .where(MaintenancePlan.org_id == ctx.org_id)
    )


async def _get(
    db: AsyncSession, ctx: Ctx, plan_id: uuid.UUID
) -> tuple[MaintenancePlan, Asset, str]:
    row = (await db.execute(_query(ctx).where(MaintenancePlan.id == plan_id))).first()
    if row is None:
        raise NotFound("Maintenance plan not found.", code="PLAN_NOT_FOUND")
    return row[0], row[1], row[2]


@router.get("", summary="Maintenance plans with next occurrence (staff)")
async def list_plans(ctx: StaffCtx, db: DB, page: PageDep) -> dict[str, Any]:
    query = _query(ctx)
    total = await count_rows(db, query)
    rows = (
        await db.execute(
            query.order_by(MaintenancePlan.title, MaintenancePlan.id)
            .offset(page.offset)
            .limit(page.page_size)
        )
    ).all()
    return page_body([await _view(db, p, a, c) for p, a, c in rows], total, page)


@router.post("", status_code=201, summary="Create a plan for an active asset (staff)")
async def create_plan(body: PlanCreate, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    asset = (
        await db.execute(select(Asset).where(Asset.id == body.asset_id, Asset.org_id == ctx.org_id))
    ).scalar_one_or_none()
    if asset is None:
        raise Unprocessable("Unknown asset.", code="ASSET_NOT_FOUND")
    if asset.status != AssetStatus.ACTIVE:
        # ASSET-04 / PM-01: plans may only be created for active assets.
        raise Conflict(
            f"This asset is {asset.status}; maintenance plans need an active asset.",
            code="ASSET_NOT_ACTIVE",
        )
    category = (
        await db.execute(
            select(ServiceCategory).where(
                ServiceCategory.id == body.category_id, ServiceCategory.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    if category is None or not category.is_enabled:
        raise Unprocessable("Unknown or disabled category.", code="CATEGORY_NOT_FOUND")
    plan = MaintenancePlan(org_id=ctx.org_id, created_by_id=ctx.user.id, **body.model_dump())
    db.add(plan)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="maintenance.plan_created",
        target_type="maintenance_plan",
        target_id=plan.id,
        summary=f"Maintenance plan created: {plan.title}",
        after=body.model_dump(mode="json"),
    )
    await db.commit()
    return await _view(db, plan, asset, category.name)


@router.get("/{plan_id}", summary="Plan detail with generated request history (staff)")
async def get_plan(plan_id: uuid.UUID, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    plan, asset, category_name = await _get(db, ctx, plan_id)
    view = await _view(db, plan, asset, category_name)
    history = await db.scalars(
        select(ServiceRequest)
        .where(ServiceRequest.maintenance_plan_id == plan.id)
        .order_by(ServiceRequest.occurrence_date.desc())
        .limit(50)
    )
    view["generated"] = [
        {
            "request_id": str(r.id),
            "reference": request_ref(r.number),
            "occurrence_date": r.occurrence_date.isoformat() if r.occurrence_date else None,
            "status": r.status,
            "created_at": iso(r.created_at),
        }
        for r in history
    ]
    return view


@router.patch("/{plan_id}", summary="Edit, enable, or disable a plan (staff)")
async def update_plan(plan_id: uuid.UUID, body: PlanPatch, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    plan, asset, category_name = await _get(db, ctx, plan_id)
    changes = body.model_dump(exclude_none=True, mode="json")
    if changes.get("is_enabled") and asset.status != AssetStatus.ACTIVE:
        raise Conflict("The asset is not active.", code="ASSET_NOT_ACTIVE")
    before = {key: getattr(plan, key) for key in changes}
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(plan, key, value)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="maintenance.plan_updated",
        target_type="maintenance_plan",
        target_id=plan.id,
        summary=f"Maintenance plan updated: {plan.title}",
        before=before,
        after=changes,
    )
    await db.commit()
    return await _view(db, plan, asset, category_name)


@router.post(
    "/generate",
    summary="Generate due occurrences up to a date (staff; safe to repeat)",
)
async def generate_now(
    body: GenerateBody, ctx: StaffCtx, db: DB, idempotency_key: IdempotencyHeader = None
) -> Any:
    scope = "maintenance.generate"
    if (
        replay := await idempotency.begin(db, ctx, scope, idempotency_key, body.model_dump())
    ) is not None:
        return replay
    if body.plan_id is not None:
        await _get(db, ctx, body.plan_id)
    created = await generate(db, ctx.org, body.as_of, plan_id=body.plan_id, actor_id=ctx.user.id)
    result = {
        "as_of": body.as_of.isoformat(),
        "generated_count": len(created),
        "generated": created,
    }
    await idempotency.finish(db, ctx, scope, idempotency_key, 200, result)
    await db.commit()
    return result
