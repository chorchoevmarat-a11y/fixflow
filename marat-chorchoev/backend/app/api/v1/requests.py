"""Service-request intake, queue, and the server-enforced lifecycle (REQ-*, LIFE-*)."""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime, Field
from sqlalchemy import case, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body, CommandId, Quantity, Reason
from app.api.v1.catalog import usable_property_clause
from app.config import settings
from app.core.deps import DB, Ctx, CurrentCtx, RequesterCtx, StaffCtx, TechnicianCtx
from app.core.errors import Conflict, Forbidden, Unprocessable
from app.core.security import payload_hash
from app.models.base import utcnow
from app.models.models import (
    Asset,
    AssetServiceHistory,
    AssetStatus,
    Assignment,
    AssignmentStatus,
    AuditEvent,
    EvidenceFile,
    EvidenceKind,
    Feedback,
    NoteVisibility,
    NotificationType,
    Organization,
    Priority,
    Property,
    RequestStatus,
    Role,
    ServiceCategory,
    ServiceRequest,
    Skill,
    SlaState,
    TechnicianProfile,
    User,
    WorkNote,
)
from app.services import idempotency, inventory, scheduling, sla
from app.services import requests as svc
from app.services.common import (
    PageDep,
    audit,
    count_rows,
    iso,
    load_calendar,
    notify,
    page_body,
    request_ref,
    staff_user_ids,
)
from app.services.idempotency import IdempotencyHeader

router = APIRouter(prefix="/requests", tags=["requests"])
R = ServiceRequest
S = RequestStatus

# ---------------------------------------------------------------------------
# Bodies
# ---------------------------------------------------------------------------


class RequestCreate(Body):
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=20, max_length=3000)
    category_id: uuid.UUID
    property_id: uuid.UUID
    asset_id: uuid.UUID | None = None
    priority: Priority = Priority.NORMAL
    preferred_start_at: AwareDatetime | None = None
    preferred_end_at: AwareDatetime | None = None


class TriageBody(Body):
    triage_notes: str | None = Field(default=None, max_length=3000)
    category_id: uuid.UUID | None = None
    priority: Priority | None = None
    reason: str | None = Field(default=None, min_length=3, max_length=1000)


class ReclassifyBody(Body):
    category_id: uuid.UUID | None = None
    priority: Priority | None = None
    reason: Reason


class DuplicateBody(Body):
    duplicate_of_id: uuid.UUID | None = Field(description="null clears the link")


class AssignBody(Body):
    technician_id: uuid.UUID
    start_at: AwareDatetime
    end_at: AwareDatetime


class RescheduleBody(AssignBody):
    reason: str | None = Field(default=None, max_length=1000)


class ReasonBody(Body):
    reason: Reason


class OptionalReasonBody(Body):
    reason: str | None = Field(default=None, min_length=3, max_length=1000)


class UnblockBody(Body):
    resolution_note: Reason


class MaterialLine(Body):
    item_id: uuid.UUID
    quantity: Quantity
    client_command_id: CommandId


class CompleteBody(Body):
    completion_note: str = Field(min_length=20, max_length=3000)
    materials: list[MaterialLine] = Field(default_factory=list, max_length=20)


class FeedbackBody(Body):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# Intake and queue
# ---------------------------------------------------------------------------

SortKey = Literal["newest", "oldest", "priority", "due"]
_PRIORITY_RANK = case((R.priority == Priority.HIGH, 3), (R.priority == Priority.NORMAL, 2), else_=1)


async def _category_for_use(db: AsyncSession, ctx: Ctx, category_id: uuid.UUID) -> ServiceCategory:
    category = (
        await db.execute(
            select(ServiceCategory).where(
                ServiceCategory.id == category_id, ServiceCategory.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    if category is None:
        raise Unprocessable("Unknown category.", code="CATEGORY_NOT_FOUND")
    if not category.is_enabled:
        raise Unprocessable(
            "This category is disabled and cannot be used for new work.", code="CATEGORY_DISABLED"
        )
    return category


def _norm(column: Any) -> Any:
    """Case- and whitespace-insensitive form of a text column."""
    return func.lower(func.trim(func.regexp_replace(column, r"\s+", " ", "g")))


def _norm_text(value: str) -> str:
    return " ".join(value.split()).lower()


async def _find_identical_open_request(
    db: AsyncSession, ctx: Ctx, body: RequestCreate
) -> ServiceRequest | None:
    """An unfinished request by this requester with the same place, category, priority and wording."""
    # Serialize concurrent identical submissions: without this, N simultaneous sends all pass
    # the check below and create N requests. The lock is released when the transaction ends.
    lock_key = "|".join(
        [
            str(ctx.org_id),
            str(ctx.user.id),
            str(body.property_id),
            str(body.asset_id),
            str(body.category_id),
            str(body.priority),
            _norm_text(body.title),
            _norm_text(body.description),
        ]
    )
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0))))
    return (
        await db.execute(
            select(R)
            .where(
                R.org_id == ctx.org_id,
                R.requester_id == ctx.user.id,
                R.property_id == body.property_id,
                R.asset_id.is_(None) if body.asset_id is None else R.asset_id == body.asset_id,
                R.category_id == body.category_id,
                R.priority == body.priority,
                R.status.not_in([S.CLOSED, S.CANCELED, S.COMPLETED]),
                _norm(R.title) == _norm_text(body.title),
                _norm(R.description) == _norm_text(body.description),
            )
            .order_by(R.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


@router.post(
    "",
    status_code=201,
    summary="Create a service request (an identical open one is returned instead, HTTP 200)",
    responses={422: {"description": "Validation failed or property/asset not allowed"}},
)
async def create_request(
    body: RequestCreate, ctx: CurrentCtx, db: DB, idempotency_key: IdempotencyHeader = None
) -> Any:
    if ctx.is_technician:
        raise Forbidden("Technicians cannot create requests.", code="ROLE_FORBIDDEN")
    if (
        replay := await idempotency.begin(
            db, ctx, "request.create", idempotency_key, body.model_dump()
        )
    ) is not None:
        return replay
    if (
        body.preferred_start_at
        and body.preferred_end_at
        and body.preferred_end_at <= body.preferred_start_at
    ):
        raise Unprocessable(
            "Preferred visit must end after it starts.", code="PREFERRED_INTERVAL_INVALID"
        )
    latest_preferred = body.preferred_end_at or body.preferred_start_at
    if latest_preferred is not None and latest_preferred <= utcnow():
        raise Unprocessable(
            "Preferred visit must be in the future.", code="PREFERRED_INTERVAL_IN_PAST"
        )
    await _category_for_use(db, ctx, body.category_id)
    prop = (
        await db.execute(
            select(Property).where(
                Property.id == body.property_id,
                Property.org_id == ctx.org_id,
                usable_property_clause(ctx),
            )
        )
    ).scalar_one_or_none()
    if prop is None:
        # ASSET-03: foreign or unauthorized ids are rejected, never silently accepted.
        raise Unprocessable(
            "You are not allowed to file requests for this property.", code="PROPERTY_NOT_ALLOWED"
        )
    if body.asset_id is not None:
        asset = (
            await db.execute(
                select(Asset).where(
                    Asset.id == body.asset_id,
                    Asset.org_id == ctx.org_id,
                    Asset.property_id == prop.id,
                )
            )
        ).scalar_one_or_none()
        if asset is None:
            raise Unprocessable(
                "This asset does not belong to the selected property.", code="ASSET_NOT_ALLOWED"
            )
        if asset.status == AssetStatus.RETIRED:
            raise Unprocessable("This asset is retired.", code="ASSET_RETIRED")

    existing = await _find_identical_open_request(db, ctx, body)
    if existing is not None:
        # Spam guard: the same person re-sending the same open request gets the original back.
        result = {**await svc.detail(db, ctx, existing), "deduplicated": True}
        await idempotency.finish(db, ctx, "request.create", idempotency_key, 200, result)
        await db.commit()
        return JSONResponse(jsonable_encoder(result), status_code=200)

    number = await db.scalar(
        update(Organization)
        .where(Organization.id == ctx.org_id)
        .values(next_request_number=Organization.next_request_number + 1)
        .returning(Organization.next_request_number - 1)
    )
    now = utcnow()
    req = R(
        id=uuid.uuid4(),
        org_id=ctx.org_id,
        number=number,
        requester_id=ctx.user.id,
        status=S.SUBMITTED,
        sla_budget_seconds=sla.budget_seconds_for(body.priority),
        sla_consumed_seconds=0,
        **body.model_dump(),
    )
    db.add(req)
    db.add(sla.start(req, await load_calendar(db, ctx.org), now))
    await db.flush()
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="request.created",
        target_type="service_request",
        target_id=req.id,
        request_id=req.id,
        summary=f"{request_ref(req.number)} created: {req.title}",
        after={"status": S.SUBMITTED.value, "priority": req.priority},
    )
    await svc.publish_request_event(db, req, "created")
    result = await svc.detail(db, ctx, req)
    await idempotency.finish(db, ctx, "request.create", idempotency_key, 201, result)
    await db.commit()
    return JSONResponse(jsonable_encoder(result), status_code=201)


@router.get("", summary="Search, filter, sort, and page through requests")
async def list_requests(
    ctx: CurrentCtx,
    db: DB,
    page: PageDep,
    q: Annotated[
        str | None, Query(max_length=120, description="Request reference/number, title, or address")
    ] = None,
    status: Annotated[list[RequestStatus] | None, Query()] = None,
    priority: Priority | None = None,
    category_id: uuid.UUID | None = None,
    technician_id: uuid.UUID | None = None,
    property_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    sla_state: SlaState | None = None,
    created_from: Annotated[date | None, Query(description="Organization-local date")] = None,
    created_to: Annotated[date | None, Query(description="Organization-local date")] = None,
    open_only: bool = False,
    sort: SortKey = "newest",
) -> dict[str, Any]:
    now = utcnow()
    query = svc.list_query(ctx)
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        conditions = [
            R.title.icontains(q.strip(), autoescape=True),
            Property.address.icontains(q.strip(), autoescape=True),
            Property.name.icontains(q.strip(), autoescape=True),
        ]
        if digits and len(digits) <= 9:
            conditions.append(R.number == int(digits))
        query = query.where(or_(*conditions))
    if status:
        query = query.where(R.status.in_(status))
    if not status or S.CANCELED not in status:
        hide_before = now - timedelta(minutes=settings.CANCELED_HIDE_AFTER_MINUTES)
        query = query.where(
            or_(R.status != S.CANCELED, R.canceled_at.is_(None), R.canceled_at > hide_before)
        )
    if open_only:
        query = query.where(R.status.not_in([S.CLOSED, S.CANCELED, S.COMPLETED]))
    if priority is not None:
        query = query.where(R.priority == priority)
    if category_id is not None:
        query = query.where(R.category_id == category_id)
    if property_id is not None:
        query = query.where(R.property_id == property_id)
    if asset_id is not None:
        query = query.where(R.asset_id == asset_id)
    if technician_id is not None:
        query = query.where(Assignment.technician_id == technician_id)
    if sla_state is not None:
        query = query.where(sla.sla_state_expr(now) == sla_state.value)
    tz = ZoneInfo(ctx.org.timezone)
    if created_from is not None:
        query = query.where(R.created_at >= datetime.combine(created_from, time(0), tz))
    if created_to is not None:
        query = query.where(
            R.created_at < datetime.combine(created_to + timedelta(days=1), time(0), tz)
        )

    total = await count_rows(db, query)
    order = {
        "newest": [R.created_at.desc()],
        "oldest": [R.created_at.asc()],
        "priority": [_PRIORITY_RANK.desc(), R.created_at.asc()],
        "due": [R.sla_due_at.asc().nulls_last(), R.created_at.asc()],
    }[sort]
    rows = (
        await db.execute(query.order_by(*order, R.id).offset(page.offset).limit(page.page_size))
    ).all()
    cal = await load_calendar(db, ctx.org)
    return page_body([svc.list_row(row, cal, now) for row in rows], total, page)


@router.get("/{request_id}", summary="Request detail with allowed actions")
async def get_request(request_id: uuid.UUID, ctx: CurrentCtx, db: DB) -> dict[str, Any]:
    return await svc.detail(db, ctx, await svc.get_request(db, ctx, request_id))


@router.get("/{request_id}/activity", summary="Chronological activity timeline")
async def request_activity(
    request_id: uuid.UUID, ctx: CurrentCtx, db: DB, page: PageDep
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id)
    query = (
        select(AuditEvent, User.full_name)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.request_id == req.id, AuditEvent.org_id == ctx.org_id)
    )
    if not ctx.is_staff:
        query = query.where(AuditEvent.is_public.is_(True))
    total = await count_rows(db, query)
    rows = await db.execute(
        query.order_by(AuditEvent.created_at, AuditEvent.id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return page_body(
        [
            {
                "id": str(event.id),
                "action": event.action,
                "summary": event.summary,
                "actor_name": actor_name or "System",
                "created_at": iso(event.created_at),
                "before": event.before,
                "after": event.after,
            }
            for event, actor_name in rows
        ],
        total,
        page,
    )


# ---------------------------------------------------------------------------
# Triage and classification (dispatcher / admin)
# ---------------------------------------------------------------------------


async def _apply_classification(
    db: AsyncSession,
    ctx: Ctx,
    req: ServiceRequest,
    category_id: uuid.UUID | None,
    priority: Priority | None,
    reason: str | None,
) -> bool:
    """Apply category/priority changes with audit + SLA recalculation. True if changed."""
    category_changed = category_id is not None and category_id != req.category_id
    priority_changed = priority is not None and priority != req.priority
    if not (category_changed or priority_changed):
        return False
    if not reason:
        raise Unprocessable(
            "A reason is required to change category or priority.", code="REASON_REQUIRED"
        )
    if category_changed and category_id is not None:
        category = await _category_for_use(db, ctx, category_id)
        old_name = await db.scalar(
            select(ServiceCategory.name).where(ServiceCategory.id == req.category_id)
        )
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="request.category_changed",
            target_type="service_request",
            target_id=req.id,
            request_id=req.id,
            summary=f"Category changed from {old_name} to {category.name}: {reason}",
            before={"category_id": str(req.category_id), "category": old_name},
            after={"category_id": str(category.id), "category": category.name, "reason": reason},
        )
        req.category_id = category.id
    if priority_changed and priority is not None:
        old_priority = req.priority
        before_budget = req.sla_budget_seconds
        db.add(sla.change_priority(req, await load_calendar(db, ctx.org), utcnow(), priority))
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="request.priority_changed",
            target_type="service_request",
            target_id=req.id,
            request_id=req.id,
            summary=f"Priority changed from {old_priority} to {priority.value}: {reason}",
            before={"priority": old_priority, "sla_budget_seconds": before_budget},
            after={
                "priority": priority.value,
                "sla_budget_seconds": req.sla_budget_seconds,
                "sla_consumed_seconds": req.sla_consumed_seconds,
                "reason": reason,
            },
        )
    return True


@router.post("/{request_id}/triage", summary="SUBMITTED / REOPENED -> TRIAGED (staff)")
async def triage(request_id: uuid.UUID, body: TriageBody, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    svc.require_status(req, S.SUBMITTED, S.REOPENED, action="triage")
    await _apply_classification(db, ctx, req, body.category_id, body.priority, body.reason)
    if body.triage_notes is not None:
        req.triage_notes = body.triage_notes
    await svc.record_transition(
        db,
        ctx,
        req,
        S.TRIAGED,
        action="triaged",
        summary="Request triaged",
        after={"triage_notes": body.triage_notes} if body.triage_notes else None,
        is_public=True,
    )
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post(
    "/{request_id}/reclassify", summary="Change category or priority with a reason (staff)"
)
async def reclassify(
    request_id: uuid.UUID, body: ReclassifyBody, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    if req.status in (S.CLOSED, S.CANCELED, S.COMPLETED):
        raise Conflict(f"A {req.status} request cannot be reclassified.", code="INVALID_TRANSITION")
    if (
        body.category_id is not None
        and body.category_id != req.category_id
        and req.status not in (S.SUBMITTED, S.TRIAGED, S.REOPENED)
    ):
        raise Conflict(
            "Unassign the technician before changing the category.",
            code="CATEGORY_LOCKED_WHILE_ASSIGNED",
        )
    changed = await _apply_classification(
        db, ctx, req, body.category_id, body.priority, body.reason
    )
    if not changed:
        raise Unprocessable("Nothing to change.", code="NO_CHANGE")
    await svc.publish_request_event(db, req, "reclassified")
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post("/{request_id}/duplicate", summary="Link or unlink a duplicate request (staff)")
async def mark_duplicate(
    request_id: uuid.UUID, body: DuplicateBody, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    before = {"duplicate_of_id": str(req.duplicate_of_id) if req.duplicate_of_id else None}
    summary = "Duplicate link removed"
    if body.duplicate_of_id is not None:
        if body.duplicate_of_id == req.id:
            raise Unprocessable("A request cannot duplicate itself.", code="DUPLICATE_SELF")
        # Same-organization lookup: a foreign id is indistinguishable from a missing one.
        other = (
            await db.execute(select(R).where(R.id == body.duplicate_of_id, R.org_id == ctx.org_id))
        ).scalar_one_or_none()
        if other is None:
            raise Unprocessable("Related request not found.", code="DUPLICATE_NOT_FOUND")
        summary = f"Marked as duplicate of {request_ref(other.number)}"
    req.duplicate_of_id = body.duplicate_of_id
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="request.duplicate_linked",
        target_type="service_request",
        target_id=req.id,
        request_id=req.id,
        summary=summary,
        before=before,
        after={"duplicate_of_id": str(body.duplicate_of_id) if body.duplicate_of_id else None},
        is_public=False,
    )
    await svc.publish_request_event(db, req, "duplicate_linked")
    await db.commit()
    return await svc.detail(db, ctx, req)


# ---------------------------------------------------------------------------
# Scheduling and dispatch
# ---------------------------------------------------------------------------


@router.get("/{request_id}/candidates", summary="Technician candidates for a slot (staff)")
async def candidates(
    request_id: uuid.UUID,
    ctx: StaffCtx,
    db: DB,
    start_at: AwareDatetime,
    end_at: AwareDatetime,
    eligible_only: bool = False,
    skill_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id)
    slot_error = None
    try:
        scheduling.validate_slot(start_at, end_at, utcnow())
    except Unprocessable as exc:
        slot_error = {"code": exc.code, "message": exc.message}
    result = await scheduling.evaluate(
        db,
        ctx.org,
        category_id=req.category_id,
        start_at=start_at,
        end_at=end_at,
        exclude_request_id=req.id,
    )
    if slot_error is not None:
        for candidate in result:
            candidate["eligible"] = False
            candidate["reasons"].insert(0, slot_error)
    if skill_id is not None:
        skill_name = await db.scalar(
            select(Skill.name).where(Skill.id == skill_id, Skill.org_id == ctx.org_id)
        )
        result = [c for c in result if skill_name in c["skills"]]
    if eligible_only:
        result = [c for c in result if c["eligible"]]
    return {"slot_error": slot_error, "candidates": result}


@router.get(
    "/{request_id}/suggestions",
    summary="Smart slot finder: earliest eligible technician and slot (staff)",
)
async def suggestions(request_id: uuid.UUID, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id)
    svc.require_status(req, S.TRIAGED, action="find slots for")
    category = await db.get(ServiceCategory, req.category_id)
    duration = category.default_duration_minutes if category else 60
    options = await scheduling.suggest(
        db,
        ctx.org,
        category_id=req.category_id,
        duration_minutes=duration,
        now=utcnow(),
        preferred_start=req.preferred_start_at,
    )
    return {"duration_minutes": duration, "options": options}


async def _lock_technician(
    db: AsyncSession, ctx: Ctx, technician_id: uuid.UUID
) -> TechnicianProfile:
    """Row lock that serializes every scheduling decision for one technician (SCHED-04)."""
    profile = (
        await db.execute(
            select(TechnicianProfile)
            .where(TechnicianProfile.id == technician_id, TechnicianProfile.org_id == ctx.org_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if profile is None:
        raise Unprocessable("Unknown technician.", code="TECHNICIAN_NOT_FOUND")
    return profile


async def _book(
    db: AsyncSession,
    ctx: Ctx,
    req: ServiceRequest,
    technician_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
) -> tuple[Assignment, TechnicianProfile]:
    """Validate eligibility and insert the reservation. Raises 409 on a schedule clash."""
    scheduling.validate_slot(start_at, end_at, utcnow())
    profile = await _lock_technician(db, ctx, technician_id)
    verdict = (
        await scheduling.evaluate(
            db,
            ctx.org,
            category_id=req.category_id,
            start_at=start_at,
            end_at=end_at,
            technician_ids=[profile.id],
            exclude_request_id=req.id,
        )
    )[0]
    if not verdict["eligible"]:
        codes = {reason["code"] for reason in verdict["reasons"]}
        if codes == {"SCHEDULE_CONFLICT"}:
            raise Conflict(
                "The technician already has a job in this time slot.",
                code="SCHEDULE_CONFLICT",
                details={"conflicts": verdict["conflicts"]},
            )
        raise Unprocessable(
            "The technician is not eligible for this appointment.",
            code="TECHNICIAN_NOT_ELIGIBLE",
            details={"reasons": verdict["reasons"]},
        )
    assignment = Assignment(
        org_id=ctx.org_id,
        request_id=req.id,
        technician_id=profile.id,
        technician_no=profile.technician_no,
        start_at=start_at,
        end_at=end_at,
        status=AssignmentStatus.SCHEDULED,
        is_active=True,
        assigned_by_id=ctx.user.id,
    )
    db.add(assignment)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Storage-level backstop: the exclusion constraint refused an overlap.
        if "ex_assignments_no_overlap" in str(exc.orig):
            raise Conflict(
                "The technician already has a job in this time slot.", code="SCHEDULE_CONFLICT"
            ) from None
        raise
    return assignment, profile


def _end_assignment(assignment: Assignment, status: AssignmentStatus, reason: str | None) -> None:
    assignment.status = status
    assignment.is_active = False
    assignment.ended_at = utcnow()
    assignment.ended_reason = reason


def _slot_text(ctx: Ctx, start_at: datetime, end_at: datetime) -> str:
    tz = ZoneInfo(ctx.org.timezone)
    return f"{start_at.astimezone(tz):%d %b %Y %H:%M}-{end_at.astimezone(tz):%H:%M}"


@router.post(
    "/{request_id}/assign",
    summary="TRIAGED -> SCHEDULED: assign an eligible technician (staff)",
    responses={409: {"description": "Schedule conflict or invalid state"}},
)
async def assign(
    request_id: uuid.UUID,
    body: AssignBody,
    ctx: StaffCtx,
    db: DB,
    idempotency_key: IdempotencyHeader = None,
) -> Any:
    scope = f"request.assign:{request_id}"
    if (
        replay := await idempotency.begin(db, ctx, scope, idempotency_key, body.model_dump())
    ) is not None:
        return replay
    req = await svc.get_request(db, ctx, request_id, lock=True)
    svc.require_status(req, S.TRIAGED, action="assign")
    assignment, profile = await _book(db, ctx, req, body.technician_id, body.start_at, body.end_at)
    technician_name = await db.scalar(select(User.full_name).where(User.id == profile.user_id))
    await svc.record_transition(
        db,
        ctx,
        req,
        S.SCHEDULED,
        action="assigned",
        summary=f"Assigned to {technician_name} for {_slot_text(ctx, body.start_at, body.end_at)}",
        after={
            "assignment_id": str(assignment.id),
            "technician": technician_name,
            "start_at": iso(body.start_at),
            "end_at": iso(body.end_at),
        },
        technician_users=(profile.user_id,),
    )
    await notify(
        db,
        org_id=ctx.org_id,
        recipient_ids=[profile.user_id],
        type=NotificationType.ASSIGNMENT_NEW,
        title=f"New job: {request_ref(req.number)}",
        body=f"{req.title} — {_slot_text(ctx, body.start_at, body.end_at)}",
        request_id=req.id,
    )
    result = await svc.detail(db, ctx, req)
    await idempotency.finish(db, ctx, scope, idempotency_key, 200, result)
    await db.commit()
    return result


@router.post(
    "/{request_id}/reschedule",
    summary="Move the appointment or change technician before work begins (staff)",
)
async def reschedule(
    request_id: uuid.UUID,
    body: RescheduleBody,
    ctx: StaffCtx,
    db: DB,
    idempotency_key: IdempotencyHeader = None,
) -> Any:
    scope = f"request.reschedule:{request_id}"
    if (
        replay := await idempotency.begin(db, ctx, scope, idempotency_key, body.model_dump())
    ) is not None:
        return replay
    req = await svc.get_request(db, ctx, request_id, lock=True)
    svc.require_status(req, S.SCHEDULED, S.ACCEPTED, action="reschedule")
    previous = await svc.active_assignment(db, req.id)
    previous_user = await svc.technician_user_id(db, previous)
    if previous is not None:
        # The old reservation is kept as history (LIFE-03 / SCHED-06).
        _end_assignment(previous, AssignmentStatus.RESCHEDULED, body.reason)
        await db.flush()
    assignment, profile = await _book(db, ctx, req, body.technician_id, body.start_at, body.end_at)
    technician_name = await db.scalar(select(User.full_name).where(User.id == profile.user_id))
    await svc.record_transition(
        db,
        ctx,
        req,
        S.SCHEDULED,
        action="rescheduled",
        summary=f"Rescheduled to {technician_name}, {_slot_text(ctx, body.start_at, body.end_at)}",
        after={
            "assignment_id": str(assignment.id),
            "previous_assignment_id": str(previous.id) if previous else None,
            "technician": technician_name,
            "start_at": iso(body.start_at),
            "end_at": iso(body.end_at),
            "reason": body.reason,
        },
        technician_users=(profile.user_id, previous_user),
    )
    same_technician = previous_user == profile.user_id
    await notify(
        db,
        org_id=ctx.org_id,
        recipient_ids=[profile.user_id],
        type=NotificationType.ASSIGNMENT_CHANGED
        if same_technician
        else NotificationType.ASSIGNMENT_NEW,
        title=f"{'Rescheduled' if same_technician else 'New job'}: {request_ref(req.number)}",
        body=f"{req.title} — {_slot_text(ctx, body.start_at, body.end_at)}",
        request_id=req.id,
    )
    if previous_user is not None and not same_technician:
        await notify(
            db,
            org_id=ctx.org_id,
            recipient_ids=[previous_user],
            type=NotificationType.ASSIGNMENT_CHANGED,
            title=f"Job reassigned: {request_ref(req.number)}",
            body=f"{req.title} is no longer assigned to you.",
        )
    result = await svc.detail(db, ctx, req)
    await idempotency.finish(db, ctx, scope, idempotency_key, 200, result)
    await db.commit()
    return result


@router.post("/{request_id}/unassign", summary="SCHEDULED / ACCEPTED -> TRIAGED (staff)")
async def unassign(
    request_id: uuid.UUID, body: ReasonBody, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    svc.require_status(req, S.SCHEDULED, S.ACCEPTED, action="unassign")
    assignment = await svc.active_assignment(db, req.id)
    technician_user = await svc.technician_user_id(db, assignment)
    if assignment is not None:
        _end_assignment(assignment, AssignmentStatus.UNASSIGNED, body.reason)
    await svc.record_transition(
        db,
        ctx,
        req,
        S.TRIAGED,
        action="unassigned",
        summary=f"Technician unassigned: {body.reason}",
        after={"reason": body.reason},
        technician_users=(technician_user,),
    )
    if technician_user is not None:
        await notify(
            db,
            org_id=ctx.org_id,
            recipient_ids=[technician_user],
            type=NotificationType.ASSIGNMENT_CHANGED,
            title=f"Job unassigned: {request_ref(req.number)}",
            body=f"{req.title} is no longer assigned to you.",
        )
    await db.commit()
    return await svc.detail(db, ctx, req)


# ---------------------------------------------------------------------------
# Technician workflow
# ---------------------------------------------------------------------------


@router.post("/{request_id}/accept", summary="SCHEDULED -> ACCEPTED (assigned technician)")
async def accept(request_id: uuid.UUID, ctx: TechnicianCtx, db: DB) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    assignment = await svc.require_my_assignment(db, ctx, req)
    svc.require_status(req, S.SCHEDULED, action="accept")
    assignment.status = AssignmentStatus.ACCEPTED
    await svc.record_transition(
        db,
        ctx,
        req,
        S.ACCEPTED,
        action="accepted",
        summary=f"{ctx.user.full_name} accepted the job",
        technician_users=(ctx.user.id,),
    )
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post("/{request_id}/decline", summary="Decline before starting -> TRIAGED (technician)")
async def decline(
    request_id: uuid.UUID, body: ReasonBody, ctx: TechnicianCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    assignment = await svc.require_my_assignment(db, ctx, req)
    svc.require_status(req, S.SCHEDULED, S.ACCEPTED, action="decline")
    _end_assignment(assignment, AssignmentStatus.DECLINED, body.reason)
    await svc.record_transition(
        db,
        ctx,
        req,
        S.TRIAGED,
        action="declined",
        summary=f"{ctx.user.full_name} declined the job: {body.reason}",
        after={"reason": body.reason},
        is_public=False,
        technician_users=(ctx.user.id,),
    )
    await notify(
        db,
        org_id=ctx.org_id,
        recipient_ids=await staff_user_ids(db, ctx.org_id),
        type=NotificationType.ASSIGNMENT_DECLINED,
        title=f"{request_ref(req.number)} declined by {ctx.user.full_name}",
        body=body.reason,
        request_id=req.id,
    )
    await db.commit()
    # The technician no longer has access to the request.
    return {"id": str(req.id), "status": req.status}


@router.post(
    "/{request_id}/start",
    summary="ACCEPTED -> IN_PROGRESS (assigned technician; estimate gate applies)",
    responses={409: {"description": "Invalid state or estimate not approved"}},
)
async def start(request_id: uuid.UUID, ctx: TechnicianCtx, db: DB) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    await svc.require_my_assignment(db, ctx, req)
    svc.require_status(req, S.ACCEPTED, action="start")
    blocker = svc.start_blocker(await svc.current_estimate(db, req.id))
    if blocker is not None:
        raise Conflict(blocker, code="ESTIMATE_NOT_APPROVED")
    await svc.record_transition(
        db,
        ctx,
        req,
        S.IN_PROGRESS,
        action="started",
        summary=f"{ctx.user.full_name} started work",
        technician_users=(ctx.user.id,),
    )
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post("/{request_id}/block", summary="IN_PROGRESS -> BLOCKED with a reason (technician)")
async def block(
    request_id: uuid.UUID, body: ReasonBody, ctx: TechnicianCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    await svc.require_my_assignment(db, ctx, req)
    svc.require_status(req, S.IN_PROGRESS, action="block")
    req.blocker_reason = body.reason
    await svc.record_transition(
        db,
        ctx,
        req,
        S.BLOCKED,
        action="blocked",
        summary=f"Work blocked: {body.reason}",
        after={"reason": body.reason},
        technician_users=(ctx.user.id,),
    )
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post("/{request_id}/unblock", summary="BLOCKED -> IN_PROGRESS with a resolution note")
async def unblock(
    request_id: uuid.UUID, body: UnblockBody, ctx: TechnicianCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    await svc.require_my_assignment(db, ctx, req)
    svc.require_status(req, S.BLOCKED, action="unblock")
    await svc.record_transition(
        db,
        ctx,
        req,
        S.IN_PROGRESS,
        action="unblocked",
        summary=f"Blocker resolved: {body.resolution_note}",
        after={"resolution_note": body.resolution_note, "blocker_reason": req.blocker_reason},
        technician_users=(ctx.user.id,),
    )
    req.blocker_reason = None
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post(
    "/{request_id}/complete",
    summary="IN_PROGRESS -> COMPLETED with note, evidence, and optional materials (technician)",
)
async def complete(
    request_id: uuid.UUID, body: CompleteBody, ctx: TechnicianCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    assignment = await svc.require_my_assignment(db, ctx, req)
    svc.require_status(req, S.IN_PROGRESS, action="complete")
    images = await db.scalar(
        select(func.count())
        .select_from(EvidenceFile)
        .where(
            EvidenceFile.request_id == req.id,
            EvidenceFile.kind == EvidenceKind.COMPLETION,
            EvidenceFile.assignment_id == assignment.id,
        )
    )
    if not images:
        raise Unprocessable(
            "Upload at least one completion photo before completing the job.",
            code="COMPLETION_EVIDENCE_REQUIRED",
        )
    # Any failing line raises and rolls the whole completion back (LIFE-05 / API-05).
    for line in body.materials:
        await inventory.consume(db, ctx, req, line.item_id, line.quantity, line.client_command_id)

    now = utcnow()
    _end_assignment(assignment, AssignmentStatus.COMPLETED, None)
    req.completion_note = body.completion_note
    req.completed_at = now
    if (event := sla.stop(req, await load_calendar(db, ctx.org), now, "completed")) is not None:
        db.add(event)
    db.add(
        WorkNote(
            org_id=ctx.org_id,
            request_id=req.id,
            author_id=ctx.user.id,
            author_role=Role.TECHNICIAN,
            body=body.completion_note,
            visibility=NoteVisibility.PUBLIC,
            assignment_id=assignment.id,
            client_command_id=f"completion:{assignment.id}",
            payload_hash=payload_hash({"completion": body.completion_note}),
        )
    )
    if req.asset_id is not None:
        db.add(
            AssetServiceHistory(
                org_id=ctx.org_id,
                asset_id=req.asset_id,
                request_id=req.id,
                technician_user_id=ctx.user.id,
                serviced_at=now,
                outcome=body.completion_note,
            )
        )
    await svc.record_transition(
        db,
        ctx,
        req,
        S.COMPLETED,
        action="completed",
        summary=f"{ctx.user.full_name} completed the job",
        after={"completion_note": body.completion_note, "sla_outcome": req.sla_final_state},
        technician_users=(ctx.user.id,),
    )
    await notify(
        db,
        org_id=ctx.org_id,
        recipient_ids=[req.requester_id, *await staff_user_ids(db, ctx.org_id)],
        type=NotificationType.JOB_COMPLETED,
        title=f"{request_ref(req.number)} completed",
        body=f"{req.title} — please review the work.",
        request_id=req.id,
    )
    await db.commit()
    return await svc.detail(db, ctx, req)


# ---------------------------------------------------------------------------
# Closure, rework, cancellation, feedback
# ---------------------------------------------------------------------------


@router.post(
    "/{request_id}/close", summary="COMPLETED -> CLOSED (requester, or staff with a reason)"
)
async def close(
    request_id: uuid.UUID, body: OptionalReasonBody, ctx: CurrentCtx, db: DB
) -> dict[str, Any]:
    if ctx.is_technician:
        raise Forbidden("Technicians cannot close requests.", code="ROLE_FORBIDDEN")
    req = await svc.get_request(db, ctx, request_id, lock=True)
    svc.require_status(req, S.COMPLETED, action="close")
    if ctx.is_staff and not body.reason:
        raise Unprocessable(
            "A reason is required when staff close a request.", code="REASON_REQUIRED"
        )
    req.closed_at = utcnow()
    await svc.record_transition(
        db,
        ctx,
        req,
        S.CLOSED,
        action="closed",
        summary="Request closed" + (f": {body.reason}" if body.reason else " by requester"),
        after={"reason": body.reason} if body.reason else None,
    )
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post("/{request_id}/reopen", summary="COMPLETED -> REOPENED: request rework (requester)")
async def reopen(
    request_id: uuid.UUID, body: ReasonBody, ctx: RequesterCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    svc.require_status(req, S.COMPLETED, action="reopen")
    await svc.record_transition(
        db,
        ctx,
        req,
        S.REOPENED,
        action="reopened",
        summary=f"Rework requested: {body.reason}",
        after={"reason": body.reason},
    )
    await notify(
        db,
        org_id=ctx.org_id,
        recipient_ids=await staff_user_ids(db, ctx.org_id),
        type=NotificationType.REWORK_REQUESTED,
        title=f"Rework requested on {request_ref(req.number)}",
        body=body.reason,
        request_id=req.id,
    )
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post(
    "/{request_id}/cancel", summary="Cancel (requester: SUBMITTED; staff: up to SCHEDULED)"
)
async def cancel(
    request_id: uuid.UUID, body: OptionalReasonBody, ctx: CurrentCtx, db: DB
) -> dict[str, Any]:
    if ctx.is_technician:
        raise Forbidden("Technicians cannot cancel requests.", code="ROLE_FORBIDDEN")
    req = await svc.get_request(db, ctx, request_id, lock=True)
    if ctx.is_staff:
        svc.require_status(req, S.SUBMITTED, S.TRIAGED, S.SCHEDULED, action="cancel")
        if not body.reason:
            raise Unprocessable("A reason is required to cancel.", code="REASON_REQUIRED")
    else:
        svc.require_status(req, S.SUBMITTED, action="cancel")
    assignment = await svc.active_assignment(db, req.id)
    technician_user = await svc.technician_user_id(db, assignment)
    if assignment is not None:
        _end_assignment(assignment, AssignmentStatus.CANCELED, body.reason)
    now = utcnow()
    req.canceled_at = now
    if (event := sla.stop(req, await load_calendar(db, ctx.org), now, "canceled")) is not None:
        db.add(event)
    await svc.record_transition(
        db,
        ctx,
        req,
        S.CANCELED,
        action="canceled",
        summary="Request canceled" + (f": {body.reason}" if body.reason else ""),
        after={"reason": body.reason} if body.reason else None,
        technician_users=(technician_user,),
    )
    if technician_user is not None:
        await notify(
            db,
            org_id=ctx.org_id,
            recipient_ids=[technician_user],
            type=NotificationType.ASSIGNMENT_CHANGED,
            title=f"Job canceled: {request_ref(req.number)}",
            body=f"{req.title} was canceled.",
        )
    await db.commit()
    return await svc.detail(db, ctx, req)


@router.post("/{request_id}/feedback", status_code=201, summary="Satisfaction feedback (requester)")
async def give_feedback(
    request_id: uuid.UUID, body: FeedbackBody, ctx: RequesterCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    svc.require_status(req, S.COMPLETED, S.CLOSED, action="leave feedback on")
    if await db.scalar(select(exists().where(Feedback.request_id == req.id))):
        raise Conflict("Feedback was already submitted.", code="FEEDBACK_EXISTS")
    db.add(
        Feedback(
            org_id=ctx.org_id,
            request_id=req.id,
            requester_id=ctx.user.id,
            rating=body.rating,
            comment=body.comment,
        )
    )
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="request.feedback",
        target_type="service_request",
        target_id=req.id,
        request_id=req.id,
        summary=f"Requester rated the work {body.rating}/5",
        after={"rating": body.rating, "comment": body.comment},
    )
    await svc.publish_request_event(db, req, "feedback")
    await db.commit()
    return await svc.detail(db, ctx, req)
