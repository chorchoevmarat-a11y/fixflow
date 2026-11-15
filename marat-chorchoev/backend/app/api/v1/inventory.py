"""Inventory items, stock additions, and material consumption (INV-01..06)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body, CommandId, Money, Quantity
from app.core.deps import DB, AdminCtx, Ctx, CurrentCtx, StaffCtx, TechnicianCtx
from app.core.errors import Conflict, Forbidden, NotFound
from app.models.models import (
    InventoryItem,
    MaterialUsage,
    RequestStatus,
    StockMovement,
    StockMovementKind,
    User,
)
from app.services import events, inventory
from app.services import requests as svc
from app.services.common import PageDep, audit, count_rows, iso, page_body

router = APIRouter(tags=["inventory"])


class ItemCreate(Body):
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z0-9._/-]+$")
    name: str = Field(min_length=2, max_length=200)
    unit: str = Field(min_length=1, max_length=30)
    stock_quantity: int = Field(default=0, ge=0, le=10_000_000)
    reorder_threshold: int = Field(default=0, ge=0, le=10_000_000)
    unit_price_minor: Money = 0


class ItemPatch(Body):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    reorder_threshold: int | None = Field(default=None, ge=0, le=10_000_000)
    unit_price_minor: Money | None = None
    is_active: bool | None = None


class StockAdditionBody(Body):
    quantity: Quantity
    reason: str = Field(min_length=3, max_length=300)


class ConsumeBody(Body):
    item_id: uuid.UUID
    quantity: Quantity
    client_command_id: CommandId


def _item_view(item: InventoryItem, ctx: Ctx) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(item.id),
        "code": item.code,
        "name": item.name,
        "unit": item.unit,
        "stock_quantity": item.stock_quantity,
        "is_active": item.is_active,
    }
    if ctx.is_staff:
        view.update(
            {
                "reorder_threshold": item.reorder_threshold,
                "unit_price_minor": item.unit_price_minor,
                "currency": ctx.org.currency,
                "is_low_stock": item.stock_quantity <= item.reorder_threshold,
            }
        )
    return view


async def _get_item(db: AsyncSession, ctx: Ctx, item_id: uuid.UUID) -> InventoryItem:
    item = (
        await db.execute(
            select(InventoryItem).where(
                InventoryItem.id == item_id, InventoryItem.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise NotFound("Inventory item not found.", code="ITEM_NOT_FOUND")
    return item


@router.get("/inventory", summary="Inventory items (staff: full; technician: usable items)")
async def list_items(
    ctx: CurrentCtx,
    db: DB,
    page: PageDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    low_stock: bool = False,
    include_inactive: bool = False,
) -> dict[str, Any]:
    if ctx.is_requester:
        raise Forbidden("Requesters cannot view inventory.", code="ROLE_FORBIDDEN")
    query = select(InventoryItem).where(InventoryItem.org_id == ctx.org_id)
    if not (ctx.is_staff and include_inactive):
        query = query.where(InventoryItem.is_active.is_(True))
    if low_stock:
        query = query.where(InventoryItem.stock_quantity <= InventoryItem.reorder_threshold)
    if q:
        query = query.where(
            or_(
                InventoryItem.name.icontains(q, autoescape=True),
                InventoryItem.code.icontains(q, autoescape=True),
            )
        )
    total = await count_rows(db, query)
    items = await db.scalars(
        query.order_by(InventoryItem.name, InventoryItem.id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return page_body([_item_view(item, ctx) for item in items], total, page)


@router.post("/inventory", status_code=201, summary="Create an item (admin)")
async def create_item(body: ItemCreate, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    if await db.scalar(
        select(InventoryItem.id).where(
            InventoryItem.org_id == ctx.org_id,
            func.lower(InventoryItem.code) == body.code.lower(),
        )
    ):
        raise Conflict("An item with this code already exists.", code="ITEM_CODE_EXISTS")
    item = InventoryItem(org_id=ctx.org_id, **body.model_dump())
    db.add(item)
    await db.flush()
    if body.stock_quantity > 0:
        db.add(
            StockMovement(
                org_id=ctx.org_id,
                item_id=item.id,
                kind=StockMovementKind.ADDITION,
                quantity_delta=body.stock_quantity,
                balance_after=body.stock_quantity,
                reason="Opening stock",
                actor_id=ctx.user.id,
            )
        )
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="inventory.item_created",
        target_type="inventory_item",
        target_id=item.id,
        summary=f"Inventory item created: {item.code} {item.name}",
        after=body.model_dump(),
    )
    await db.commit()
    return _item_view(item, ctx)


@router.patch("/inventory/{item_id}", summary="Update an item (admin)")
async def update_item(item_id: uuid.UUID, body: ItemPatch, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    item = await _get_item(db, ctx, item_id)
    changes = body.model_dump(exclude_none=True)
    before = {key: getattr(item, key) for key in changes}
    for key, value in changes.items():
        setattr(item, key, value)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="inventory.item_updated",
        target_type="inventory_item",
        target_id=item.id,
        summary=f"Inventory item updated: {item.code}",
        before=before,
        after=changes,
    )
    await db.commit()
    return _item_view(item, ctx)


@router.post("/inventory/{item_id}/stock-additions", status_code=201, summary="Add stock (admin)")
async def add_stock(
    item_id: uuid.UUID, body: StockAdditionBody, ctx: AdminCtx, db: DB
) -> dict[str, Any]:
    balance = await db.scalar(
        update(InventoryItem)
        .where(InventoryItem.id == item_id, InventoryItem.org_id == ctx.org_id)
        .values(stock_quantity=InventoryItem.stock_quantity + body.quantity)
        .returning(InventoryItem.stock_quantity)
    )
    if balance is None:
        raise NotFound("Inventory item not found.", code="ITEM_NOT_FOUND")
    db.add(
        StockMovement(
            org_id=ctx.org_id,
            item_id=item_id,
            kind=StockMovementKind.ADDITION,
            quantity_delta=body.quantity,
            balance_after=balance,
            reason=body.reason,
            actor_id=ctx.user.id,
        )
    )
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="inventory.stock_added",
        target_type="inventory_item",
        target_id=item_id,
        summary=f"Stock added: +{body.quantity} ({body.reason})",
        after={"quantity": body.quantity, "balance_after": balance, "reason": body.reason},
    )
    await events.publish(db, ctx.org_id, "inventory.updated", staff=True, item_id=item_id)
    await db.commit()
    item = await _get_item(db, ctx, item_id)
    await db.refresh(item)
    return _item_view(item, ctx)


@router.get("/inventory/{item_id}/movements", summary="Stock movement history (staff)")
async def item_movements(
    item_id: uuid.UUID, ctx: StaffCtx, db: DB, page: PageDep
) -> dict[str, Any]:
    item = await _get_item(db, ctx, item_id)
    query = (
        select(StockMovement, User.full_name)
        .join(User, User.id == StockMovement.actor_id)
        .where(StockMovement.item_id == item.id)
    )
    total = await count_rows(db, query)
    rows = await db.execute(
        query.order_by(StockMovement.created_at.desc(), StockMovement.id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return page_body(
        [
            {
                "id": str(m.id),
                "kind": m.kind,
                "quantity_delta": m.quantity_delta,
                "balance_after": m.balance_after,
                "reason": m.reason,
                "actor_name": actor,
                "created_at": iso(m.created_at),
            }
            for m, actor in rows
        ],
        total,
        page,
    )


# ---------------------------------------------------------------------------
# Material usage on a request
# ---------------------------------------------------------------------------


def _usage_view(usage: MaterialUsage, item: InventoryItem, technician_name: str, ctx: Ctx) -> dict:
    view: dict[str, Any] = {
        "id": str(usage.id),
        "item_id": str(usage.item_id),
        "item_code": item.code,
        "item_name": item.name,
        "unit": item.unit,
        "quantity": usage.quantity,
        "technician_name": technician_name,
        "client_command_id": usage.client_command_id,
        "created_at": iso(usage.created_at),
    }
    if not ctx.is_technician:
        view.update(
            {
                "unit_price_minor": usage.unit_price_minor,
                "total_minor": usage.total_minor,
                "currency": ctx.org.currency,
            }
        )
    return view


async def _usage_views(
    db: AsyncSession, ctx: Ctx, request_id: uuid.UUID, usage_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    query = (
        select(MaterialUsage, InventoryItem, User.full_name)
        .join(InventoryItem, InventoryItem.id == MaterialUsage.item_id)
        .join(User, User.id == MaterialUsage.technician_user_id)
        .where(MaterialUsage.request_id == request_id, MaterialUsage.org_id == ctx.org_id)
        .order_by(MaterialUsage.created_at, MaterialUsage.id)
        .limit(500)
    )
    if usage_id is not None:
        query = query.where(MaterialUsage.id == usage_id)
    return [_usage_view(u, i, name, ctx) for u, i, name in await db.execute(query)]


@router.get("/requests/{request_id}/materials", summary="Materials used on a request")
async def request_materials(request_id: uuid.UUID, ctx: CurrentCtx, db: DB) -> list[dict[str, Any]]:
    req = await svc.get_request(db, ctx, request_id)
    return await _usage_views(db, ctx, req.id)


@router.post(
    "/requests/{request_id}/materials",
    status_code=201,
    summary="Consume stock on an in-progress job (assigned technician; replay safe)",
    responses={
        200: {"description": "Replay of an already-applied command"},
        409: {"description": "Insufficient stock, wrong state, or command id reused"},
    },
)
async def consume_material(
    request_id: uuid.UUID, body: ConsumeBody, ctx: TechnicianCtx, db: DB
) -> JSONResponse:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    # A replay returns the original result even if the job has moved on since.
    replay = await inventory.find_replay(
        db, ctx, req.id, body.item_id, body.quantity, body.client_command_id
    )
    if replay is None:
        await svc.require_my_assignment(db, ctx, req)
        svc.require_status(req, RequestStatus.IN_PROGRESS, action="record materials on")
    usage, replayed = await inventory.consume(
        db, ctx, req, body.item_id, body.quantity, body.client_command_id
    )
    if not replayed:
        await svc.publish_request_event(db, req, "material_consumed", (ctx.user.id,))
    await db.commit()
    view = (await _usage_views(db, ctx, req.id, usage.id))[0]
    return JSONResponse(
        view,
        status_code=200 if replayed else 201,
        headers={"Idempotency-Replayed": "true"} if replayed else None,
    )
