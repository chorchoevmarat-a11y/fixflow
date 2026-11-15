"""Atomic, replay-safe material consumption (INV-03..05)."""

import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Ctx
from app.core.errors import Conflict, NotFound
from app.core.security import payload_hash
from app.models.models import (
    InventoryItem,
    MaterialUsage,
    ServiceRequest,
    StockMovement,
    StockMovementKind,
)
from app.services import events
from app.services.common import audit, request_ref


def _digest(request_id: uuid.UUID, item_id: uuid.UUID, quantity: int) -> str:
    return payload_hash({"request_id": request_id, "item_id": item_id, "quantity": quantity})


async def find_replay(
    db: AsyncSession,
    ctx: Ctx,
    request_id: uuid.UUID,
    item_id: uuid.UUID,
    quantity: int,
    client_command_id: str,
) -> MaterialUsage | None:
    """The usage created by an earlier delivery of this command, if any."""
    existing = (
        await db.execute(
            select(MaterialUsage).where(
                MaterialUsage.org_id == ctx.org_id,
                MaterialUsage.client_command_id == client_command_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return None
    if existing.technician_user_id != ctx.user.id or existing.payload_hash != _digest(
        request_id, item_id, quantity
    ):
        raise Conflict(
            "This command id was already used for a different operation.",
            code="COMMAND_ID_REUSED",
        )
    return existing


async def consume(
    db: AsyncSession,
    ctx: Ctx,
    req: ServiceRequest,
    item_id: uuid.UUID,
    quantity: int,
    client_command_id: str,
) -> tuple[MaterialUsage, bool]:
    """Decrement stock and record usage in one transaction. Returns (usage, replayed)."""
    replay = await find_replay(db, ctx, req.id, item_id, quantity, client_command_id)
    if replay is not None:
        return replay, True

    try:
        async with db.begin_nested():
            # Single conditional UPDATE: the row lock serializes concurrent consumers and
            # the predicate guarantees stock can never go below zero (INV-04).
            row = (
                await db.execute(
                    update(InventoryItem)
                    .where(
                        InventoryItem.id == item_id,
                        InventoryItem.org_id == ctx.org_id,
                        InventoryItem.is_active.is_(True),
                        InventoryItem.stock_quantity >= quantity,
                    )
                    .values(stock_quantity=InventoryItem.stock_quantity - quantity)
                    .returning(
                        InventoryItem.stock_quantity,
                        InventoryItem.unit_price_minor,
                        InventoryItem.name,
                        InventoryItem.unit,
                    )
                )
            ).first()
            if row is None:
                item = (
                    await db.execute(
                        select(InventoryItem).where(
                            InventoryItem.id == item_id, InventoryItem.org_id == ctx.org_id
                        )
                    )
                ).scalar_one_or_none()
                if item is None or not item.is_active:
                    raise NotFound("Inventory item not found.", code="ITEM_NOT_FOUND")
                raise Conflict(
                    f"Not enough stock of {item.name}: {item.stock_quantity} {item.unit} left.",
                    code="INSUFFICIENT_STOCK",
                    details={"available": item.stock_quantity, "requested": quantity},
                )
            balance, unit_price, name, unit = row
            usage = MaterialUsage(
                org_id=ctx.org_id,
                request_id=req.id,
                item_id=item_id,
                technician_user_id=ctx.user.id,
                quantity=quantity,
                unit_price_minor=unit_price,  # price snapshot at consumption time (INV-05)
                total_minor=quantity * unit_price,
                client_command_id=client_command_id,
                payload_hash=_digest(req.id, item_id, quantity),
            )
            db.add(usage)
            db.add(
                StockMovement(
                    org_id=ctx.org_id,
                    item_id=item_id,
                    kind=StockMovementKind.CONSUMPTION,
                    quantity_delta=-quantity,
                    balance_after=balance,
                    reason=f"Used on {request_ref(req.number)}",
                    actor_id=ctx.user.id,
                )
            )
            await db.flush()
    except IntegrityError as exc:
        if "uq_material_usage_command" not in str(exc.orig):
            raise
        # A concurrent delivery of the same command won; the savepoint undid our decrement.
        replay = await find_replay(db, ctx, req.id, item_id, quantity, client_command_id)
        if replay is None:
            raise
        return replay, True

    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="material.consumed",
        target_type="material_usage",
        target_id=usage.id,
        request_id=req.id,
        summary=f"Used {quantity} {unit} of {name}",
        after={
            "item_id": str(item_id),
            "quantity": quantity,
            "unit_price_minor": unit_price,
            "total_minor": usage.total_minor,
            "stock_after": balance,
        },
    )
    await events.publish(db, ctx.org_id, "inventory.updated", staff=True, item_id=item_id)
    return usage, False
