import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_membership
from app.database import get_db
from app.models.models import (
    InventoryItem,
    InventoryTransaction,
    InventoryTransactionType,
    MaterialUsage,
    OrganizationMembership,
    ServiceRequest,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


class ItemCreate(BaseModel):
    name: str
    description: str | None = None
    sku: str | None = None
    unit: str = "each"
    unit_cost: float = 0.0
    stock_quantity: float = 0.0
    min_stock_level: float | None = None
    location: str | None = None


class RestockRequest(BaseModel):
    quantity: float
    unit_cost: float | None = None
    notes: str | None = None


class ConsumeRequest(BaseModel):
    service_request_id: uuid.UUID
    quantity: float
    client_command_id: str | None = None  # Idempotency key
    notes: str | None = None


@router.get("")
async def list_inventory(
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    query = select(InventoryItem).where(
        InventoryItem.organization_id == membership.organization_id,
        InventoryItem.is_active == True,
    )
    if search:
        query = query.where(InventoryItem.name.ilike(f"%{search}%") | InventoryItem.sku.ilike(f"%{search}%"))

    total = await db.scalar(
        select(func.count(InventoryItem.id)).where(
            InventoryItem.organization_id == membership.organization_id,
            InventoryItem.is_active == True,
        )
    ) or 0

    res = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = res.scalars().all()

    return {
        "items": [
            {
                "id": str(i.id),
                "name": i.name,
                "sku": i.sku,
                "unit": i.unit,
                "unit_cost": float(i.unit_cost),
                "stock_quantity": float(i.stock_quantity),
                "min_stock_level": float(i.min_stock_level) if i.min_stock_level is not None else None,
                "location": i.location,
            }
            for i in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: ItemCreate,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    item = InventoryItem(
        organization_id=membership.organization_id,
        name=payload.name,
        description=payload.description,
        sku=payload.sku,
        unit=payload.unit,
        unit_cost=Decimal(str(payload.unit_cost)),
        stock_quantity=Decimal(str(payload.stock_quantity)),
        min_stock_level=Decimal(str(payload.min_stock_level)) if payload.min_stock_level is not None else None,
        location=payload.location,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": str(item.id), "name": item.name, "stock_quantity": float(item.stock_quantity)}


@router.post("/{item_id}/restock")
async def restock_item(
    item_id: uuid.UUID,
    payload: RestockRequest,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    item = await db.get(InventoryItem, item_id)
    if not item or item.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Item not found")

    qty = Decimal(str(payload.quantity))
    item.stock_quantity = item.stock_quantity + qty

    tx = InventoryTransaction(
        item_id=item.id,
        transaction_type=InventoryTransactionType.RESTOCK,
        quantity=qty,
        unit_cost=Decimal(str(payload.unit_cost)) if payload.unit_cost else item.unit_cost,
        performed_by_id=membership.user_id,
        notes=payload.notes,
    )
    db.add(tx)

    await db.commit()
    await db.refresh(item)
    return {"id": str(item.id), "new_stock_quantity": float(item.stock_quantity)}


@router.post("/{item_id}/consume")
async def consume_item(
    item_id: uuid.UUID,
    payload: ConsumeRequest,
    membership: Annotated[OrganizationMembership, Depends(get_current_membership)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # Check idempotency
    if payload.client_command_id:
        existing = await db.execute(
            select(MaterialUsage).where(MaterialUsage.client_command_id == payload.client_command_id)
        )
        found = existing.scalar_one_or_none()
        if found:
            return {
                "id": str(found.id),
                "status": "already_processed",
                "quantity": float(found.quantity),
                "total_cost": float(found.total_cost),
            }

    item = await db.get(InventoryItem, item_id)
    if not item or item.organization_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Item not found")

    sr = await db.get(ServiceRequest, payload.service_request_id)
    if not sr or sr.org_id != membership.organization_id:
        raise HTTPException(status_code=404, detail="Service request not found")

    qty = Decimal(str(payload.quantity))
    if item.stock_quantity < qty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Current: {item.stock_quantity}, requested: {qty}",
        )

    item.stock_quantity = item.stock_quantity - qty
    total_cost = qty * item.unit_cost

    usage = MaterialUsage(
        service_request_id=payload.service_request_id,
        item_id=item.id,
        recorded_by_id=membership.user_id,
        quantity=qty,
        unit_cost=item.unit_cost,
        total_cost=total_cost,
        client_command_id=payload.client_command_id,
        notes=payload.notes,
    )
    db.add(usage)

    tx = InventoryTransaction(
        item_id=item.id,
        transaction_type=InventoryTransactionType.CONSUMPTION,
        quantity=qty,
        unit_cost=item.unit_cost,
        reference_id=sr.id,
        performed_by_id=membership.user_id,
        notes=payload.notes,
    )
    db.add(tx)

    await db.commit()
    await db.refresh(usage)
    return {
        "id": str(usage.id),
        "status": "consumed",
        "quantity": float(usage.quantity),
        "total_cost": float(usage.total_cost),
    }
