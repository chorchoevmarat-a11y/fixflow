"""Service categories, properties, and equipment assets."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import ColumnElement, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body
from app.core.deps import DB, AdminCtx, Ctx, CurrentCtx, StaffCtx
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models.models import (
    OPEN_STATUSES,
    Asset,
    AssetServiceHistory,
    AssetStatus,
    CategorySkill,
    EvidenceFile,
    InventoryItem,
    MaintenancePlan,
    MaterialUsage,
    OrganizationMembership,
    Property,
    PropertyRequester,
    Role,
    ServiceCategory,
    ServiceRequest,
    Skill,
    User,
)
from app.services.common import PageDep, audit, count_rows, iso, page_body, request_ref
from app.services.maintenance import next_occurrence

router = APIRouter()

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class CategoryCreate(Body):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=2000)
    default_duration_minutes: int = Field(default=60, ge=30, le=24 * 60)
    skill_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class CategoryPatch(Body):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    default_duration_minutes: int | None = Field(default=None, ge=30, le=24 * 60)
    is_enabled: bool | None = None
    skill_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


async def _category_views(
    db: AsyncSession, org_id: uuid.UUID, where: ColumnElement[bool] | None = None
) -> list[dict[str, Any]]:
    query = select(ServiceCategory).where(ServiceCategory.org_id == org_id)
    if where is not None:
        query = query.where(where)
    categories = list(await db.scalars(query.order_by(ServiceCategory.name)))
    skills: dict[uuid.UUID, list[dict[str, str]]] = {c.id: [] for c in categories}
    if categories:
        for category_id, skill_id, name in await db.execute(
            select(CategorySkill.category_id, Skill.id, Skill.name)
            .join(Skill, Skill.id == CategorySkill.skill_id)
            .where(CategorySkill.org_id == org_id)
            .order_by(Skill.name)
        ):
            if category_id in skills:
                skills[category_id].append({"id": str(skill_id), "name": name})
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description,
            "default_duration_minutes": c.default_duration_minutes,
            "is_enabled": c.is_enabled,
            "required_skills": skills[c.id],
        }
        for c in categories
    ]


async def _set_category_skills(
    db: AsyncSession, ctx: Ctx, category_id: uuid.UUID, skill_ids: list[uuid.UUID]
) -> None:
    wanted = set(skill_ids)
    valid = set(
        await db.scalars(select(Skill.id).where(Skill.org_id == ctx.org_id, Skill.id.in_(wanted)))
    )
    if valid != wanted:
        raise Unprocessable("Unknown skill id.", code="SKILL_NOT_FOUND")
    await db.execute(delete(CategorySkill).where(CategorySkill.category_id == category_id))
    for skill_id in sorted(wanted, key=str):
        db.add(CategorySkill(org_id=ctx.org_id, category_id=category_id, skill_id=skill_id))


@router.get("/categories", tags=["categories"], summary="Service categories")
async def list_categories(
    ctx: CurrentCtx, db: DB, enabled_only: bool = False
) -> list[dict[str, Any]]:
    where = ServiceCategory.is_enabled.is_(True) if enabled_only else None
    return await _category_views(db, ctx.org_id, where)


@router.post("/categories", tags=["categories"], status_code=201, summary="Create (admin)")
async def create_category(body: CategoryCreate, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    if await db.scalar(
        select(ServiceCategory.id).where(
            ServiceCategory.org_id == ctx.org_id,
            func.lower(ServiceCategory.name) == body.name.lower(),
        )
    ):
        raise Conflict("A category with this name already exists.", code="CATEGORY_EXISTS")
    category = ServiceCategory(
        org_id=ctx.org_id,
        name=body.name,
        description=body.description,
        default_duration_minutes=body.default_duration_minutes,
    )
    db.add(category)
    await db.flush()
    await _set_category_skills(db, ctx, category.id, body.skill_ids)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="category.created",
        target_type="category",
        target_id=category.id,
        summary=f"Category created: {body.name}",
        after=body.model_dump(mode="json"),
    )
    await db.commit()
    return (await _category_views(db, ctx.org_id, ServiceCategory.id == category.id))[0]


@router.patch("/categories/{category_id}", tags=["categories"], summary="Update (admin)")
async def update_category(
    category_id: uuid.UUID, body: CategoryPatch, ctx: AdminCtx, db: DB
) -> dict[str, Any]:
    category = (
        await db.execute(
            select(ServiceCategory).where(
                ServiceCategory.id == category_id, ServiceCategory.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    if category is None:
        raise NotFound("Category not found.", code="CATEGORY_NOT_FOUND")
    before = {
        "name": category.name,
        "description": category.description,
        "default_duration_minutes": category.default_duration_minutes,
        "is_enabled": category.is_enabled,
    }
    if body.name is not None and body.name.lower() != category.name.lower():
        if await db.scalar(
            select(ServiceCategory.id).where(
                ServiceCategory.org_id == ctx.org_id,
                func.lower(ServiceCategory.name) == body.name.lower(),
            )
        ):
            raise Conflict("A category with this name already exists.", code="CATEGORY_EXISTS")
    for field in ("name", "description", "default_duration_minutes", "is_enabled"):
        value = getattr(body, field)
        if value is not None:
            setattr(category, field, value)
    if body.skill_ids is not None:
        await _set_category_skills(db, ctx, category.id, body.skill_ids)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="category.updated",
        target_type="category",
        target_id=category.id,
        summary=f"Category updated: {category.name}",
        before=before,
        after=body.model_dump(mode="json", exclude_none=True),
    )
    await db.commit()
    return (await _category_views(db, ctx.org_id, ServiceCategory.id == category.id))[0]


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class PropertyCreate(Body):
    name: str = Field(min_length=2, max_length=200)
    address: str = Field(min_length=5, max_length=500)
    contact_instructions: str | None = Field(default=None, max_length=2000)
    is_shared: bool = True
    requester_membership_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


class PropertyPatch(Body):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    address: str | None = Field(default=None, min_length=5, max_length=500)
    contact_instructions: str | None = Field(default=None, max_length=2000)
    is_shared: bool | None = None
    is_active: bool | None = None
    requester_membership_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)


def usable_property_clause(ctx: Ctx) -> ColumnElement[bool]:
    """Properties this member may file a request for (ASSET-03)."""
    if ctx.is_staff:
        return Property.is_active.is_(True)
    return Property.is_active.is_(True) & or_(
        Property.is_shared.is_(True),
        exists(
            select(PropertyRequester.property_id).where(
                PropertyRequester.property_id == Property.id,
                PropertyRequester.membership_id == ctx.membership.id,
            )
        ),
    )


async def _property_view(db: AsyncSession, ctx: Ctx, prop: Property) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": str(prop.id),
        "name": prop.name,
        "address": prop.address,
        "contact_instructions": prop.contact_instructions,
        "is_shared": prop.is_shared,
        "is_active": prop.is_active,
    }
    if ctx.is_staff:
        rows = await db.execute(
            select(OrganizationMembership.id, User.full_name)
            .join(PropertyRequester, PropertyRequester.membership_id == OrganizationMembership.id)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(PropertyRequester.property_id == prop.id)
            .order_by(User.full_name)
        )
        view["requesters"] = [{"membership_id": str(m), "full_name": name} for m, name in rows]
        view["asset_count"] = await db.scalar(
            select(func.count()).select_from(Asset).where(Asset.property_id == prop.id)
        )
    return view


async def _set_property_requesters(
    db: AsyncSession, ctx: Ctx, property_id: uuid.UUID, membership_ids: list[uuid.UUID]
) -> None:
    wanted = set(membership_ids)
    valid = set(
        await db.scalars(
            select(OrganizationMembership.id).where(
                OrganizationMembership.org_id == ctx.org_id,
                OrganizationMembership.role == Role.REQUESTER,
                OrganizationMembership.id.in_(wanted),
            )
        )
    )
    if valid != wanted:
        raise Unprocessable(
            "Only requesters of this organization can be granted access.",
            code="REQUESTER_NOT_FOUND",
        )
    await db.execute(delete(PropertyRequester).where(PropertyRequester.property_id == property_id))
    for membership_id in sorted(wanted, key=str):
        db.add(
            PropertyRequester(
                org_id=ctx.org_id, property_id=property_id, membership_id=membership_id
            )
        )


async def _get_property(db: AsyncSession, ctx: Ctx, property_id: uuid.UUID) -> Property:
    prop = (
        await db.execute(
            select(Property).where(Property.id == property_id, Property.org_id == ctx.org_id)
        )
    ).scalar_one_or_none()
    if prop is None:
        raise NotFound("Property not found.", code="PROPERTY_NOT_FOUND")
    return prop


@router.get("/properties", tags=["properties"], summary="Service properties")
async def list_properties(
    ctx: CurrentCtx,
    db: DB,
    page: PageDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_inactive: bool = False,
) -> dict[str, Any]:
    if ctx.is_technician:
        raise Forbidden("Technicians see properties through their jobs.", code="ROLE_FORBIDDEN")
    query = select(Property).where(Property.org_id == ctx.org_id)
    if ctx.is_staff and include_inactive:
        pass
    else:
        query = query.where(usable_property_clause(ctx))
    if q:
        query = query.where(
            or_(
                Property.name.icontains(q, autoescape=True),
                Property.address.icontains(q, autoescape=True),
            )
        )
    total = await count_rows(db, query)
    props = await db.scalars(
        query.order_by(Property.name, Property.id).offset(page.offset).limit(page.page_size)
    )
    return page_body([await _property_view(db, ctx, p) for p in props], total, page)


@router.post("/properties", tags=["properties"], status_code=201, summary="Create (staff)")
async def create_property(body: PropertyCreate, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    if await db.scalar(
        select(Property.id).where(
            Property.org_id == ctx.org_id, func.lower(Property.name) == body.name.lower()
        )
    ):
        raise Conflict("A property with this name already exists.", code="PROPERTY_EXISTS")
    prop = Property(
        org_id=ctx.org_id,
        name=body.name,
        address=body.address,
        contact_instructions=body.contact_instructions,
        is_shared=body.is_shared,
    )
    db.add(prop)
    await db.flush()
    await _set_property_requesters(db, ctx, prop.id, body.requester_membership_ids)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="property.created",
        target_type="property",
        target_id=prop.id,
        summary=f"Property created: {prop.name}",
        after=body.model_dump(mode="json"),
    )
    await db.commit()
    return await _property_view(db, ctx, prop)


@router.patch("/properties/{property_id}", tags=["properties"], summary="Update (staff)")
async def update_property(
    property_id: uuid.UUID, body: PropertyPatch, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    prop = await _get_property(db, ctx, property_id)
    before = {
        "name": prop.name,
        "address": prop.address,
        "contact_instructions": prop.contact_instructions,
        "is_shared": prop.is_shared,
        "is_active": prop.is_active,
    }
    if body.name is not None and body.name.lower() != prop.name.lower():
        if await db.scalar(
            select(Property.id).where(
                Property.org_id == ctx.org_id, func.lower(Property.name) == body.name.lower()
            )
        ):
            raise Conflict("A property with this name already exists.", code="PROPERTY_EXISTS")
    for field in ("name", "address", "is_shared", "is_active"):
        value = getattr(body, field)
        if value is not None:
            setattr(prop, field, value)
    if "contact_instructions" in body.model_fields_set:
        prop.contact_instructions = body.contact_instructions
    if body.requester_membership_ids is not None:
        await _set_property_requesters(db, ctx, prop.id, body.requester_membership_ids)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="property.updated",
        target_type="property",
        target_id=prop.id,
        summary=f"Property updated: {prop.name}",
        before=before,
        after=body.model_dump(mode="json", exclude_unset=True),
    )
    await db.commit()
    return await _property_view(db, ctx, prop)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class AssetCreate(Body):
    property_id: uuid.UUID
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z0-9._/-]+$")
    name: str = Field(min_length=2, max_length=200)
    asset_type: str = Field(min_length=2, max_length=100)
    serial_number: str | None = Field(default=None, max_length=120)
    installed_on: date | None = None
    status: AssetStatus = AssetStatus.ACTIVE
    notes: str | None = Field(default=None, max_length=2000)


class AssetPatch(Body):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    asset_type: str | None = Field(default=None, min_length=2, max_length=100)
    serial_number: str | None = Field(default=None, max_length=120)
    installed_on: date | None = None
    status: AssetStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


def _asset_view(asset: Asset, property_name: str | None = None) -> dict[str, Any]:
    return {
        "id": str(asset.id),
        "property_id": str(asset.property_id),
        "property_name": property_name,
        "code": asset.code,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "serial_number": asset.serial_number,
        "installed_on": asset.installed_on.isoformat() if asset.installed_on else None,
        "status": asset.status,
        "notes": asset.notes,
    }


async def _get_asset(db: AsyncSession, ctx: Ctx, asset_id: uuid.UUID) -> Asset:
    asset = (
        await db.execute(select(Asset).where(Asset.id == asset_id, Asset.org_id == ctx.org_id))
    ).scalar_one_or_none()
    if asset is None:
        raise NotFound("Asset not found.", code="ASSET_NOT_FOUND")
    return asset


@router.get("/assets", tags=["assets"], summary="Equipment assets")
async def list_assets(
    ctx: CurrentCtx,
    db: DB,
    page: PageDep,
    property_id: uuid.UUID | None = None,
    status: AssetStatus | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    if ctx.is_technician:
        raise Forbidden("Technicians see assets through their jobs.", code="ROLE_FORBIDDEN")
    query = (
        select(Asset, Property.name)
        .join(Property, Property.id == Asset.property_id)
        .where(Asset.org_id == ctx.org_id)
    )
    if ctx.is_requester:
        # Requesters only ever see assets at properties they may use, never retired ones.
        query = query.where(usable_property_clause(ctx), Asset.status != AssetStatus.RETIRED)
    if property_id is not None:
        query = query.where(Asset.property_id == property_id)
    if status is not None:
        query = query.where(Asset.status == status)
    if q:
        query = query.where(
            or_(
                Asset.name.icontains(q, autoescape=True),
                Asset.code.icontains(q, autoescape=True),
                Asset.serial_number.icontains(q, autoescape=True),
            )
        )
    total = await count_rows(db, query)
    rows = await db.execute(
        query.order_by(Asset.code, Asset.id).offset(page.offset).limit(page.page_size)
    )
    return page_body([_asset_view(a, name) for a, name in rows], total, page)


@router.post("/assets", tags=["assets"], status_code=201, summary="Create (staff)")
async def create_asset(body: AssetCreate, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    prop = await _get_property(db, ctx, body.property_id)
    if await db.scalar(select(Asset.id).where(Asset.org_id == ctx.org_id, Asset.code == body.code)):
        raise Conflict("An asset with this code already exists.", code="ASSET_CODE_EXISTS")
    asset = Asset(org_id=ctx.org_id, **body.model_dump())
    db.add(asset)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="asset.created",
        target_type="asset",
        target_id=asset.id,
        summary=f"Asset created: {asset.code} {asset.name}",
        after=body.model_dump(mode="json"),
    )
    await db.commit()
    return _asset_view(asset, prop.name)


@router.patch("/assets/{asset_id}", tags=["assets"], summary="Update or retire (staff)")
async def update_asset(
    asset_id: uuid.UUID, body: AssetPatch, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    asset = await _get_asset(db, ctx, asset_id)
    changes = body.model_dump(exclude_unset=True)
    before = {key: getattr(asset, key) for key in changes}
    for key, value in changes.items():
        if value is None and key in ("name", "asset_type", "status"):
            continue
        setattr(asset, key, value)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="asset.retired"
        if changes.get("status") == AssetStatus.RETIRED and before.get("status") != "RETIRED"
        else "asset.updated",
        target_type="asset",
        target_id=asset.id,
        summary=f"Asset updated: {asset.code}",
        before={k: (v.isoformat() if isinstance(v, date) else v) for k, v in before.items()},
        after=body.model_dump(mode="json", exclude_unset=True),
    )
    await db.commit()
    prop = await db.get(Property, asset.property_id)
    return _asset_view(asset, prop.name if prop else None)


@router.get("/assets/{asset_id}", tags=["assets"], summary="Asset detail with service context")
async def get_asset(asset_id: uuid.UUID, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    asset = await _get_asset(db, ctx, asset_id)
    prop = await db.get(Property, asset.property_id)
    open_requests = await db.execute(
        select(ServiceRequest)
        .where(ServiceRequest.asset_id == asset.id, ServiceRequest.status.in_(OPEN_STATUSES))
        .order_by(ServiceRequest.created_at.desc())
        .limit(20)
    )
    last_service = (
        await db.execute(
            select(AssetServiceHistory, ServiceRequest.number, ServiceRequest.title, User.full_name)
            .join(ServiceRequest, ServiceRequest.id == AssetServiceHistory.request_id)
            .join(User, User.id == AssetServiceHistory.technician_user_id)
            .where(AssetServiceHistory.asset_id == asset.id)
            .order_by(AssetServiceHistory.serviced_at.desc())
            .limit(1)
        )
    ).first()
    plans = list(
        await db.scalars(
            select(MaintenancePlan).where(
                MaintenancePlan.asset_id == asset.id, MaintenancePlan.is_enabled.is_(True)
            )
        )
    )
    upcoming: list[tuple[date, MaintenancePlan]] = []
    if asset.status == AssetStatus.ACTIVE:
        for plan in plans:
            due = await next_occurrence(db, plan)
            if due is not None:
                upcoming.append((due, plan))
    upcoming.sort(key=lambda pair: pair[0])
    view = _asset_view(asset, prop.name if prop else None)
    view.update(
        {
            "property_address": prop.address if prop else None,
            "open_requests": [
                {
                    "id": str(r.id),
                    "reference": request_ref(r.number),
                    "title": r.title,
                    "status": r.status,
                    "priority": r.priority,
                }
                for r in open_requests.scalars()
            ],
            "last_service": None
            if last_service is None
            else {
                "request_id": str(last_service[0].request_id),
                "reference": request_ref(last_service[1]),
                "title": last_service[2],
                "technician_name": last_service[3],
                "serviced_at": iso(last_service[0].serviced_at),
                "outcome": last_service[0].outcome,
            },
            "next_maintenance": None
            if not upcoming
            else {
                "plan_id": str(upcoming[0][1].id),
                "title": upcoming[0][1].title,
                "date": upcoming[0][0].isoformat(),
            },
        }
    )
    return view


@router.get("/assets/{asset_id}/history", tags=["assets"], summary="Service history of an asset")
async def asset_history(
    asset_id: uuid.UUID, ctx: StaffCtx, db: DB, page: PageDep
) -> dict[str, Any]:
    asset = await _get_asset(db, ctx, asset_id)
    query = (
        select(AssetServiceHistory, ServiceRequest.number, ServiceRequest.title, User.full_name)
        .join(ServiceRequest, ServiceRequest.id == AssetServiceHistory.request_id)
        .join(User, User.id == AssetServiceHistory.technician_user_id)
        .where(AssetServiceHistory.asset_id == asset.id)
    )
    total = await count_rows(db, query)
    rows = (
        await db.execute(
            query.order_by(AssetServiceHistory.serviced_at.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
    ).all()
    request_ids = [history.request_id for history, _, _, _ in rows]
    materials: dict[uuid.UUID, list[dict[str, Any]]] = {r: [] for r in request_ids}
    attachments: dict[uuid.UUID, list[dict[str, Any]]] = {r: [] for r in request_ids}
    if request_ids:
        for usage, name, unit in await db.execute(
            select(MaterialUsage, InventoryItem.name, InventoryItem.unit)
            .join(InventoryItem, InventoryItem.id == MaterialUsage.item_id)
            .where(MaterialUsage.request_id.in_(request_ids))
            .order_by(MaterialUsage.created_at)
        ):
            materials[usage.request_id].append(
                {
                    "item_name": name,
                    "unit": unit,
                    "quantity": usage.quantity,
                    "total_minor": usage.total_minor,
                }
            )
        for file in await db.scalars(
            select(EvidenceFile)
            .where(EvidenceFile.request_id.in_(request_ids))
            .order_by(EvidenceFile.created_at)
        ):
            attachments[file.request_id].append(
                {"id": str(file.id), "kind": file.kind, "original_name": file.original_name}
            )
    items = [
        {
            "id": str(history.id),
            "request_id": str(history.request_id),
            "reference": request_ref(number),
            "title": title,
            "technician_name": technician_name,
            "serviced_at": iso(history.serviced_at),
            "outcome": history.outcome,
            "materials": materials[history.request_id],
            "attachments": attachments[history.request_id],
        }
        for history, number, title, technician_name in rows
    ]
    return page_body(items, total, page)
