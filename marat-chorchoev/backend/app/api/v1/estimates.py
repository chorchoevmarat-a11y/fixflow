"""Estimates, versioning, and requester approval (EST-01..06)."""

import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body, Money, Quantity, Reason
from app.core.deps import DB, Ctx, CurrentCtx, RequesterCtx, StaffCtx
from app.core.errors import Conflict, NotFound, Unprocessable
from app.models.base import utcnow
from app.models.models import (
    Estimate,
    EstimateLine,
    EstimateStatus,
    NotificationType,
    RequestStatus,
    ServiceRequest,
    User,
)
from app.services import idempotency, sla
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

router = APIRouter(tags=["estimates"])
E = EstimateStatus


class LineBody(Body):
    description: str = Field(min_length=1, max_length=300)
    quantity: Quantity
    unit_price_minor: Money


class EstimateBody(Body):
    labor_minutes: int = Field(ge=0, le=100_000)
    labor_rate_minor: Money = Field(description="Hourly labor rate in minor units")
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[LineBody] = Field(default_factory=list, max_length=50)


class ApproveBody(Body):
    version: int = Field(ge=1, description="The version the requester is looking at")


class RejectBody(ApproveBody):
    reason: Reason


class WithdrawBody(Body):
    reason: Reason


# 10 trillion minor units (100 billion KGS): far above any real job, far below the BIGINT limit.
MAX_ESTIMATE_TOTAL_MINOR = 10**13


def labor_total(minutes: int, rate_per_hour_minor: int) -> int:
    """Round-half-up to whole minor units using integer arithmetic only (DATA-04)."""
    return (minutes * rate_per_hour_minor + 30) // 60


def _apply(estimate: Estimate, body: EstimateBody) -> list[EstimateLine]:
    lines = [
        EstimateLine(
            org_id=estimate.org_id,
            estimate_id=estimate.id,
            position=index,
            description=line.description,
            quantity=line.quantity,
            unit_price_minor=line.unit_price_minor,
            line_total_minor=line.quantity * line.unit_price_minor,
        )
        for index, line in enumerate(body.lines, start=1)
    ]
    estimate.labor_minutes = body.labor_minutes
    estimate.labor_rate_minor = body.labor_rate_minor
    estimate.labor_total_minor = labor_total(body.labor_minutes, body.labor_rate_minor)
    estimate.materials_total_minor = sum(line.line_total_minor for line in lines)
    estimate.total_minor = estimate.labor_total_minor + estimate.materials_total_minor
    if estimate.total_minor > MAX_ESTIMATE_TOTAL_MINOR:
        # Individually valid lines can still sum past BIGINT; refuse instead of a 500.
        raise Unprocessable("The estimate total is too large.", code="ESTIMATE_TOTAL_TOO_LARGE")
    estimate.notes = body.notes
    return lines


async def _views(db: AsyncSession, estimates: list[Estimate]) -> list[dict[str, Any]]:
    ids = [e.id for e in estimates]
    lines: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ids}
    names: dict[uuid.UUID, str] = {}
    if ids:
        for line in await db.scalars(
            select(EstimateLine)
            .where(EstimateLine.estimate_id.in_(ids))
            .order_by(EstimateLine.position)
        ):
            lines[line.estimate_id].append(
                {
                    "id": str(line.id),
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit_price_minor": line.unit_price_minor,
                    "line_total_minor": line.line_total_minor,
                }
            )
        user_ids = {
            u for e in estimates for u in (e.created_by_id, e.submitted_by_id, e.decided_by_id) if u
        }
        names = dict(
            (await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids))))
            .tuples()
            .all()
        )
    return [
        {
            "id": str(e.id),
            "request_id": str(e.request_id),
            "version": e.version,
            "previous_version_id": str(e.previous_version_id) if e.previous_version_id else None,
            "status": e.status,
            "labor_minutes": e.labor_minutes,
            "labor_rate_minor": e.labor_rate_minor,
            "labor_total_minor": e.labor_total_minor,
            "materials_total_minor": e.materials_total_minor,
            "total_minor": e.total_minor,
            "currency": e.currency,
            "notes": e.notes,
            "lines": lines[e.id],
            "created_by": names.get(e.created_by_id),
            "created_at": iso(e.created_at),
            "submitted_by": names.get(e.submitted_by_id) if e.submitted_by_id else None,
            "submitted_at": iso(e.submitted_at),
            "decided_by": names.get(e.decided_by_id) if e.decided_by_id else None,
            "decided_at": iso(e.decided_at),
            "decision_reason": e.decision_reason,
        }
        for e in estimates
    ]


async def _view(db: AsyncSession, estimate: Estimate) -> dict[str, Any]:
    return (await _views(db, [estimate]))[0]


async def _load(
    db: AsyncSession, ctx: Ctx, estimate_id: uuid.UUID
) -> tuple[ServiceRequest, Estimate]:
    """Lock order is always request first, then estimate."""
    request_id = await db.scalar(
        select(Estimate.request_id).where(Estimate.id == estimate_id, Estimate.org_id == ctx.org_id)
    )
    if request_id is None:
        raise NotFound("Estimate not found.", code="ESTIMATE_NOT_FOUND")
    try:
        req = await svc.get_request(db, ctx, request_id, lock=True)
    except NotFound:
        raise NotFound("Estimate not found.", code="ESTIMATE_NOT_FOUND") from None
    estimate = (
        await db.execute(select(Estimate).where(Estimate.id == estimate_id).with_for_update())
    ).scalar_one()
    if not ctx.is_staff and estimate.status == E.DRAFT:
        raise NotFound("Estimate not found.", code="ESTIMATE_NOT_FOUND")
    return req, estimate


def _require_open(req: ServiceRequest) -> None:
    if req.status in (RequestStatus.COMPLETED, RequestStatus.CLOSED, RequestStatus.CANCELED):
        raise Conflict(
            f"Estimates cannot change on a {req.status} request.", code="INVALID_TRANSITION"
        )


@router.get("/estimates", summary="Estimates across the organization (staff)")
async def list_estimates(
    ctx: StaffCtx, db: DB, page: PageDep, status: EstimateStatus | None = None
) -> dict[str, Any]:
    query = (
        select(Estimate, ServiceRequest.number, ServiceRequest.title)
        .join(ServiceRequest, ServiceRequest.id == Estimate.request_id)
        .where(Estimate.org_id == ctx.org_id)
    )
    if status is not None:
        query = query.where(Estimate.status == status)
    total = await count_rows(db, query)
    rows = (
        await db.execute(
            query.order_by(Estimate.updated_at.desc(), Estimate.id)
            .offset(page.offset)
            .limit(page.page_size)
        )
    ).all()
    views = await _views(db, [estimate for estimate, _, _ in rows])
    for view, (_, number, title) in zip(views, rows, strict=True):
        view["request_reference"] = request_ref(number)
        view["request_title"] = title
    return page_body(views, total, page)


@router.get("/requests/{request_id}/estimates", summary="All estimate versions of a request")
async def request_estimates(request_id: uuid.UUID, ctx: CurrentCtx, db: DB) -> list[dict[str, Any]]:
    req = await svc.get_request(db, ctx, request_id)
    query = select(Estimate).where(Estimate.request_id == req.id)
    if not ctx.is_staff:
        query = query.where(Estimate.status != E.DRAFT)
    return await _views(db, list(await db.scalars(query.order_by(Estimate.version.desc()))))


@router.post(
    "/requests/{request_id}/estimates",
    status_code=201,
    summary="Create a draft estimate, or a new draft version of the current one (staff)",
)
async def create_estimate(
    request_id: uuid.UUID, body: EstimateBody, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    req = await svc.get_request(db, ctx, request_id, lock=True)
    _require_open(req)
    if await db.scalar(
        select(Estimate.id).where(Estimate.request_id == req.id, Estimate.status == E.DRAFT)
    ):
        raise Conflict(
            "A draft already exists for this request. Edit or discard it.",
            code="ESTIMATE_DRAFT_EXISTS",
        )
    latest_version = await db.scalar(
        select(func.max(Estimate.version)).where(Estimate.request_id == req.id)
    )
    current = await svc.current_estimate(db, req.id)
    estimate = Estimate(
        id=uuid.uuid4(),
        org_id=ctx.org_id,
        request_id=req.id,
        version=(latest_version or 0) + 1,
        previous_version_id=current.id if current else None,
        status=E.DRAFT,
        created_by_id=ctx.user.id,
    )
    lines = _apply(estimate, body)
    db.add(estimate)
    await db.flush()
    db.add_all(lines)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="estimate.drafted",
        target_type="estimate",
        target_id=estimate.id,
        request_id=req.id,
        summary=f"Estimate v{estimate.version} drafted",
        after={"version": estimate.version, "total_minor": estimate.total_minor},
        is_public=False,
    )
    await db.commit()
    return await _view(db, estimate)


@router.put(
    "/estimates/{estimate_id}", summary="Edit a draft (staff). Submitted versions are immutable"
)
async def update_estimate(
    estimate_id: uuid.UUID, body: EstimateBody, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    req, estimate = await _load(db, ctx, estimate_id)
    _require_open(req)
    if estimate.status != E.DRAFT:
        # EST-02: changes after submission require a new version.
        raise Conflict(
            "Only drafts can be edited. Create a new version instead.", code="ESTIMATE_IMMUTABLE"
        )
    await db.execute(delete(EstimateLine).where(EstimateLine.estimate_id == estimate.id))
    await db.flush()
    db.add_all(_apply(estimate, body))
    await db.commit()
    return await _view(db, estimate)


@router.delete("/estimates/{estimate_id}", summary="Discard a draft (staff)")
async def discard_estimate(estimate_id: uuid.UUID, ctx: StaffCtx, db: DB) -> dict[str, str]:
    _, estimate = await _load(db, ctx, estimate_id)
    if estimate.status != E.DRAFT:
        raise Conflict("Only drafts can be discarded.", code="ESTIMATE_IMMUTABLE")
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="estimate.draft_discarded",
        target_type="estimate",
        target_id=estimate.id,
        request_id=estimate.request_id,
        summary=f"Draft estimate v{estimate.version} discarded",
        is_public=False,
    )
    await db.delete(estimate)
    await db.commit()
    return {"status": "deleted"}


@router.post("/estimates/{estimate_id}/submit", summary="DRAFT -> AWAITING_APPROVAL (staff)")
async def submit_estimate(estimate_id: uuid.UUID, ctx: StaffCtx, db: DB) -> dict[str, Any]:
    req, estimate = await _load(db, ctx, estimate_id)
    _require_open(req)
    if estimate.status != E.DRAFT:
        raise Conflict("This estimate was already submitted.", code="ESTIMATE_NOT_DRAFT")
    now = utcnow()
    previous = await svc.current_estimate(db, req.id)
    if previous is not None:
        previous.status = E.SUPERSEDED
        estimate.previous_version_id = previous.id
        await db.flush()
    estimate.status = E.AWAITING_APPROVAL
    estimate.submitted_at = now
    estimate.submitted_by_id = ctx.user.id
    # SLA-03: the clock pauses while the requester is deciding.
    if (
        event := sla.pause(
            req,
            await load_calendar(db, ctx.org),
            now,
            f"estimate v{estimate.version} awaiting approval",
        )
    ) is not None:
        db.add(event)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="estimate.submitted",
        target_type="estimate",
        target_id=estimate.id,
        request_id=req.id,
        summary=f"Estimate v{estimate.version} submitted for approval",
        before={"superseded_version": previous.version} if previous else None,
        after={"version": estimate.version, "total_minor": estimate.total_minor},
    )
    await notify(
        db,
        org_id=ctx.org_id,
        recipient_ids=[req.requester_id],
        type=NotificationType.ESTIMATE_SUBMITTED,
        title=f"Estimate ready for {request_ref(req.number)}",
        body=f"Version {estimate.version} needs your decision.",
        request_id=req.id,
        exclude=ctx.user.id,
    )
    await svc.publish_request_event(
        db, req, "estimate_submitted", (await _technician_user(db, req),)
    )
    await db.commit()
    return await _view(db, estimate)


async def _technician_user(db: AsyncSession, req: ServiceRequest) -> uuid.UUID | None:
    return await svc.technician_user_id(db, await svc.active_assignment(db, req.id))


async def _decide(
    db: AsyncSession,
    ctx: Ctx,
    estimate_id: uuid.UUID,
    version: int,
    decision: EstimateStatus,
    reason: str | None,
) -> dict[str, Any]:
    req, estimate = await _load(db, ctx, estimate_id)
    if req.requester_id != ctx.user.id:
        raise NotFound("Estimate not found.", code="ESTIMATE_NOT_FOUND")
    if estimate.version != version:
        # EST-06: never decide on a version other than the one the requester saw.
        raise Conflict(
            "This is not the version you reviewed. Reload and review the current estimate.",
            code="ESTIMATE_VERSION_MISMATCH",
            details={"current_version": estimate.version},
        )
    if estimate.status != E.AWAITING_APPROVAL:
        # The row lock makes this check race-free: a second simultaneous decision lands here.
        raise Conflict(
            f"This estimate is {estimate.status} and can no longer be decided.",
            code="ESTIMATE_ALREADY_DECIDED",
            details={"status": estimate.status},
        )
    now = utcnow()
    estimate.status = decision
    estimate.decided_at = now
    estimate.decided_by_id = ctx.user.id
    estimate.decision_reason = reason
    verb = "approved" if decision == E.APPROVED else "rejected"
    if (
        event := sla.resume(
            req, await load_calendar(db, ctx.org), now, f"estimate v{version} {verb}"
        )
    ) is not None:
        db.add(event)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action=f"estimate.{verb}",
        target_type="estimate",
        target_id=estimate.id,
        request_id=req.id,
        summary=f"Estimate v{version} {verb} by {ctx.user.full_name}"
        + (f": {reason}" if reason else ""),
        before={"status": E.AWAITING_APPROVAL.value},
        after={
            "status": decision.value,
            "version": version,
            "total_minor": estimate.total_minor,
            "reason": reason,
        },
    )
    technician_user = await _technician_user(db, req)
    await notify(
        db,
        org_id=ctx.org_id,
        recipient_ids=[
            *await staff_user_ids(db, ctx.org_id),
            *([technician_user] if technician_user else []),
        ],
        type=NotificationType.ESTIMATE_DECISION,
        title=f"Estimate v{version} {verb} on {request_ref(req.number)}",
        body=reason or "",
        request_id=req.id,
    )
    await svc.publish_request_event(db, req, f"estimate_{verb}", (technician_user,))
    return await _view(db, estimate)


@router.post(
    "/estimates/{estimate_id}/approve",
    summary="Approve the reviewed version (requester)",
    responses={409: {"description": "Already decided, or version mismatch"}},
)
async def approve_estimate(
    estimate_id: uuid.UUID,
    body: ApproveBody,
    ctx: RequesterCtx,
    db: DB,
    idempotency_key: IdempotencyHeader = None,
) -> Any:
    scope = f"estimate.decide:{estimate_id}"
    payload = {"decision": "approve", **body.model_dump()}
    if (replay := await idempotency.begin(db, ctx, scope, idempotency_key, payload)) is not None:
        return replay
    result = await _decide(db, ctx, estimate_id, body.version, E.APPROVED, None)
    await idempotency.finish(db, ctx, scope, idempotency_key, 200, result)
    await db.commit()
    return result


@router.post(
    "/estimates/{estimate_id}/reject",
    summary="Reject the reviewed version with a reason (requester)",
    responses={409: {"description": "Already decided, or version mismatch"}},
)
async def reject_estimate(
    estimate_id: uuid.UUID,
    body: RejectBody,
    ctx: RequesterCtx,
    db: DB,
    idempotency_key: IdempotencyHeader = None,
) -> Any:
    scope = f"estimate.decide:{estimate_id}"
    payload = {"decision": "reject", **body.model_dump()}
    if (replay := await idempotency.begin(db, ctx, scope, idempotency_key, payload)) is not None:
        return replay
    result = await _decide(db, ctx, estimate_id, body.version, E.REJECTED, body.reason)
    await idempotency.finish(db, ctx, scope, idempotency_key, 200, result)
    await db.commit()
    return result


@router.post("/estimates/{estimate_id}/withdraw", summary="Withdraw a submitted estimate (staff)")
async def withdraw_estimate(
    estimate_id: uuid.UUID, body: WithdrawBody, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    req, estimate = await _load(db, ctx, estimate_id)
    _require_open(req)
    if estimate.status not in (E.AWAITING_APPROVAL, E.APPROVED, E.REJECTED):
        raise Conflict("Only a submitted estimate can be withdrawn.", code="ESTIMATE_NOT_CURRENT")
    was = estimate.status
    estimate.status = E.SUPERSEDED
    now = utcnow()
    if (
        was == E.AWAITING_APPROVAL
        and (
            event := sla.resume(
                req,
                await load_calendar(db, ctx.org),
                now,
                f"estimate v{estimate.version} withdrawn",
            )
        )
        is not None
    ):
        db.add(event)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="estimate.withdrawn",
        target_type="estimate",
        target_id=estimate.id,
        request_id=req.id,
        summary=f"Estimate v{estimate.version} withdrawn: {body.reason}",
        before={"status": was},
        after={"status": E.SUPERSEDED.value, "reason": body.reason},
    )
    await svc.publish_request_event(
        db, req, "estimate_withdrawn", (await _technician_user(db, req),)
    )
    await db.commit()
    return await _view(db, estimate)
