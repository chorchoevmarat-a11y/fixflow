"""Service-request access rules, transitions, and serialization."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, exists, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.deps import Ctx
from app.core.errors import Conflict, Forbidden, NotFound
from app.models.base import utcnow
from app.models.models import (
    Asset,
    Assignment,
    AssignmentStatus,
    Estimate,
    EstimateStatus,
    Feedback,
    Property,
    RequestStatus,
    ServiceCategory,
    ServiceRequest,
    TechnicianProfile,
    User,
)
from app.services import events, sla
from app.services.common import audit, iso, load_calendar, request_ref, sid

R = ServiceRequest
CURRENT_ESTIMATE_STATUSES = (
    EstimateStatus.AWAITING_APPROVAL,
    EstimateStatus.APPROVED,
    EstimateStatus.REJECTED,
)
# Assignments that tie a technician to a request for visibility purposes.
_VISIBLE_ASSIGNMENT = (
    AssignmentStatus.SCHEDULED,
    AssignmentStatus.ACCEPTED,
    AssignmentStatus.COMPLETED,
)


def visibility_clause(ctx: Ctx) -> ColumnElement[bool]:
    """Row-level rule: which requests may this membership see at all (ROLE-03)."""
    if ctx.is_staff:
        return true()
    if ctx.is_requester:
        return R.requester_id == ctx.user.id
    return exists(
        select(Assignment.id)
        .join(TechnicianProfile, TechnicianProfile.id == Assignment.technician_id)
        .where(
            Assignment.request_id == R.id,
            Assignment.status.in_(_VISIBLE_ASSIGNMENT),
            TechnicianProfile.user_id == ctx.user.id,
            TechnicianProfile.org_id == ctx.org_id,
        )
    )


async def get_request(
    db: AsyncSession, ctx: Ctx, request_id: uuid.UUID, *, lock: bool = False
) -> ServiceRequest:
    """Load a request the caller may see. ``lock`` takes a row lock for a transition."""
    query = select(R).where(R.id == request_id, R.org_id == ctx.org_id, visibility_clause(ctx))
    if lock:
        query = query.with_for_update(of=R)
    req = (await db.execute(query)).scalar_one_or_none()
    if req is None:
        # Identical answer for "does not exist", "other organization" and "not yours".
        raise NotFound("Request not found.", code="REQUEST_NOT_FOUND")
    return req


async def active_assignment(db: AsyncSession, request_id: uuid.UUID) -> Assignment | None:
    return (
        await db.execute(
            select(Assignment).where(Assignment.request_id == request_id, Assignment.is_active)
        )
    ).scalar_one_or_none()


async def my_profile(db: AsyncSession, ctx: Ctx) -> TechnicianProfile | None:
    return (
        await db.execute(
            select(TechnicianProfile).where(
                TechnicianProfile.org_id == ctx.org_id, TechnicianProfile.user_id == ctx.user.id
            )
        )
    ).scalar_one_or_none()


async def require_my_assignment(db: AsyncSession, ctx: Ctx, req: ServiceRequest) -> Assignment:
    """The caller must be the technician currently holding this request."""
    assignment = await active_assignment(db, req.id)
    profile = await my_profile(db, ctx) if ctx.is_technician else None
    if assignment is None or profile is None or assignment.technician_id != profile.id:
        raise Forbidden("This job is not assigned to you any more.", code="NOT_ASSIGNED_TECHNICIAN")
    return assignment


async def technician_user_id(db: AsyncSession, assignment: Assignment | None) -> uuid.UUID | None:
    if assignment is None:
        return None
    return await db.scalar(
        select(TechnicianProfile.user_id).where(TechnicianProfile.id == assignment.technician_id)
    )


def require_status(req: ServiceRequest, *allowed: RequestStatus, action: str) -> None:
    if req.status not in allowed:
        raise Conflict(
            f"Cannot {action} a request that is {req.status}.",
            code="INVALID_TRANSITION",
            details={"current_status": req.status, "allowed_from": [s.value for s in allowed]},
        )


async def record_transition(
    db: AsyncSession,
    ctx: Ctx,
    req: ServiceRequest,
    to_status: RequestStatus,
    *,
    action: str,
    summary: str,
    after: dict[str, Any] | None = None,
    is_public: bool = True,
    technician_users: tuple[uuid.UUID | None, ...] = (),
) -> None:
    """Change status and write the audit entry in the caller's transaction (LIFE-08)."""
    old = req.status
    req.status = to_status
    req.updated_at = utcnow()
    audit(
        db,
        org_id=req.org_id,
        actor_id=ctx.user.id,
        action=f"request.{action}",
        target_type="service_request",
        target_id=req.id,
        request_id=req.id,
        summary=summary,
        before={"status": old},
        after={"status": to_status.value, **(after or {})},
        is_public=is_public,
    )
    await publish_request_event(db, req, action, technician_users)


async def publish_request_event(
    db: AsyncSession,
    req: ServiceRequest,
    action: str,
    technician_users: tuple[uuid.UUID | None, ...] = (),
) -> None:
    users = [req.requester_id, *[u for u in technician_users if u is not None]]
    await events.publish(
        db,
        req.org_id,
        "request.updated",
        staff=True,
        user_ids=users,
        request_id=req.id,
        status=req.status,
        action=action,
    )


async def current_estimate(db: AsyncSession, request_id: uuid.UUID) -> Estimate | None:
    return (
        await db.execute(
            select(Estimate).where(
                Estimate.request_id == request_id, Estimate.status.in_(CURRENT_ESTIMATE_STATUSES)
            )
        )
    ).scalar_one_or_none()


def start_blocker(estimate: Estimate | None) -> str | None:
    """EST-04: work may not start while the current estimate is pending or rejected."""
    if estimate is None or estimate.status == EstimateStatus.APPROVED:
        return None
    if estimate.status == EstimateStatus.AWAITING_APPROVAL:
        return "The estimate is awaiting the requester's approval."
    return "The estimate was rejected. The dispatcher must replace or withdraw it."


def allowed_actions(
    ctx: Ctx,
    req: ServiceRequest,
    *,
    assigned_to_me: bool,
    estimate: Estimate | None,
    has_feedback: bool,
) -> list[str]:
    s = req.status
    actions: list[str] = []
    terminal = s in (RequestStatus.CLOSED, RequestStatus.CANCELED)
    if ctx.is_staff:
        if s in (RequestStatus.SUBMITTED, RequestStatus.REOPENED):
            actions.append("triage")
        if s == RequestStatus.TRIAGED:
            actions.append("assign")
        if s in (RequestStatus.SCHEDULED, RequestStatus.ACCEPTED):
            actions += ["reschedule", "unassign"]
        if s in (RequestStatus.SUBMITTED, RequestStatus.TRIAGED, RequestStatus.SCHEDULED):
            actions.append("cancel")
        if s == RequestStatus.COMPLETED:
            actions.append("close")
        if not terminal and s != RequestStatus.COMPLETED:
            actions += ["reclassify", "mark_duplicate", "manage_estimate"]
        if not terminal:
            actions.append("add_note")
    elif ctx.is_requester:
        if s == RequestStatus.SUBMITTED:
            actions.append("cancel")
        if s == RequestStatus.COMPLETED:
            actions += ["close", "reopen"]
        if estimate is not None and estimate.status == EstimateStatus.AWAITING_APPROVAL:
            actions.append("decide_estimate")
        if s in (RequestStatus.COMPLETED, RequestStatus.CLOSED) and not has_feedback:
            actions.append("give_feedback")
        if not terminal:
            actions.append("add_note")
    elif assigned_to_me:
        if s == RequestStatus.SCHEDULED:
            actions += ["accept", "decline"]
        if s == RequestStatus.ACCEPTED:
            actions.append("decline")
            if start_blocker(estimate) is None:
                actions.append("start")
        if s == RequestStatus.IN_PROGRESS:
            actions += ["block", "complete", "consume_material", "add_evidence"]
        if s == RequestStatus.BLOCKED:
            actions.append("unblock")
        actions.append("add_note")
    return actions


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

_TechUser = aliased(User)
_Requester = aliased(User)


def _latest_assignment_id() -> Any:
    return (
        select(Assignment.id)
        .where(Assignment.request_id == R.id, Assignment.status.in_(_VISIBLE_ASSIGNMENT))
        .order_by(Assignment.created_at.desc())
        .limit(1)
        .correlate(R)
        .scalar_subquery()
    )


def list_query(ctx: Ctx) -> Any:
    """Requests joined with the display data a list row needs (no N+1 loading)."""
    return (
        select(
            R,
            Property.name,
            Property.address,
            ServiceCategory.name,
            Assignment,
            _TechUser.full_name,
            _Requester.full_name,
        )
        .join(Property, Property.id == R.property_id)
        .join(ServiceCategory, ServiceCategory.id == R.category_id)
        .join(_Requester, _Requester.id == R.requester_id)
        .outerjoin(Assignment, Assignment.id == _latest_assignment_id())
        .outerjoin(TechnicianProfile, TechnicianProfile.id == Assignment.technician_id)
        .outerjoin(_TechUser, _TechUser.id == TechnicianProfile.user_id)
        .where(R.org_id == ctx.org_id, visibility_clause(ctx))
    )


def assignment_dict(assignment: Assignment | None, technician_name: str | None) -> dict | None:
    if assignment is None:
        return None
    return {
        "id": str(assignment.id),
        "technician_id": str(assignment.technician_id),
        "technician_name": technician_name,
        "start_at": iso(assignment.start_at),
        "end_at": iso(assignment.end_at),
        "status": assignment.status,
        "is_active": assignment.is_active,
    }


def list_row(row: Any, cal: sla.Calendar, now: datetime) -> dict[str, Any]:
    req, prop_name, prop_address, category_name, assignment, tech_name, requester_name = row
    return {
        "id": str(req.id),
        "reference": request_ref(req.number),
        "title": req.title,
        "status": req.status,
        "priority": req.priority,
        "created_at": iso(req.created_at),
        "updated_at": iso(req.updated_at),
        "completed_at": iso(req.completed_at),
        "requester_name": requester_name,
        "property": {"id": str(req.property_id), "name": prop_name, "address": prop_address},
        "category": {"id": str(req.category_id), "name": category_name},
        "asset_id": sid(req.asset_id),
        "assignment": assignment_dict(assignment, tech_name),
        "sla": sla.snapshot(req, cal, now),
        "is_preventive": req.maintenance_plan_id is not None,
    }


def estimate_summary(estimate: Estimate | None) -> dict | None:
    if estimate is None:
        return None
    return {
        "id": str(estimate.id),
        "version": estimate.version,
        "status": estimate.status,
        "total_minor": estimate.total_minor,
        "currency": estimate.currency,
    }


async def detail(db: AsyncSession, ctx: Ctx, req: ServiceRequest) -> dict[str, Any]:
    now = utcnow()
    cal = await load_calendar(db, ctx.org)
    row = (await db.execute(list_query(ctx).where(R.id == req.id))).one()
    _, _, _, _, assignment, tech_name, _ = row
    prop = await db.get(Property, req.property_id)
    category = await db.get(ServiceCategory, req.category_id)
    requester = await db.get(User, req.requester_id)
    asset = await db.get(Asset, req.asset_id) if req.asset_id else None
    assert prop is not None and category is not None and requester is not None
    estimate = await current_estimate(db, req.id)
    feedback = (
        await db.execute(select(Feedback).where(Feedback.request_id == req.id))
    ).scalar_one_or_none()
    duplicate = await db.get(R, req.duplicate_of_id) if req.duplicate_of_id else None
    profile = await my_profile(db, ctx) if ctx.is_technician else None
    assigned_to_me = (
        assignment is not None
        and assignment.is_active
        and profile is not None
        and assignment.technician_id == profile.id
    )
    has_draft = False
    if ctx.is_staff:
        has_draft = bool(
            await db.scalar(
                select(func.count())
                .select_from(Estimate)
                .where(Estimate.request_id == req.id, Estimate.status == EstimateStatus.DRAFT)
            )
        )

    requester_view: dict[str, Any] = {"id": str(requester.id), "full_name": requester.full_name}
    if not ctx.is_technician:
        # Technicians get only what the job needs: a name, not contact identifiers.
        requester_view["email"] = requester.email

    body = list_row(row, cal, now)
    body.update(
        {
            "description": req.description,
            "organization": {
                "id": str(ctx.org.id),
                "name": ctx.org.name,
                "timezone": ctx.org.timezone,
            },
            "requester": requester_view,
            "property": {
                "id": str(prop.id),
                "name": prop.name,
                "address": prop.address,
                "contact_instructions": prop.contact_instructions,
            },
            "category": {
                "id": str(category.id),
                "name": category.name,
                "default_duration_minutes": category.default_duration_minutes,
                "is_enabled": category.is_enabled,
            },
            "asset": None
            if asset is None
            else {
                "id": str(asset.id),
                "code": asset.code,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "status": asset.status,
                "serial_number": asset.serial_number,
            },
            "preferred_start_at": iso(req.preferred_start_at),
            "preferred_end_at": iso(req.preferred_end_at),
            "duplicate_of": None
            if duplicate is None
            else {
                "id": str(duplicate.id),
                "reference": request_ref(duplicate.number),
                "title": duplicate.title,
            },
            "estimate": estimate_summary(estimate),
            "start_blocked_reason": start_blocker(estimate)
            if req.status == RequestStatus.ACCEPTED
            else None,
            "completion_note": req.completion_note,
            "blocker_reason": req.blocker_reason if req.status == RequestStatus.BLOCKED else None,
            "maintenance_plan_id": sid(req.maintenance_plan_id),
            "occurrence_date": req.occurrence_date.isoformat() if req.occurrence_date else None,
            "feedback": None
            if feedback is None
            else {
                "rating": feedback.rating,
                "comment": feedback.comment,
                "created_at": iso(feedback.created_at),
            },
            "closed_at": iso(req.closed_at),
            "canceled_at": iso(req.canceled_at),
            "assigned_to_me": assigned_to_me,
            "allowed_actions": allowed_actions(
                ctx,
                req,
                assigned_to_me=assigned_to_me,
                estimate=estimate,
                has_feedback=feedback is not None,
            ),
        }
    )
    if ctx.is_staff:
        body["triage_notes"] = req.triage_notes
        body["has_draft_estimate"] = has_draft
    return body
