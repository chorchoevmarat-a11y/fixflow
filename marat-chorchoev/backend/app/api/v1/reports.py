"""Dashboard, reports, schedule board, and audit timeline.

Every figure is computed from persisted rows of the caller's organization (REPORT-05).
Date ranges are organization-local calendar days, converted to UTC instants once.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, AdminCtx, Ctx, CurrentCtx, StaffCtx
from app.core.errors import Forbidden, Unprocessable
from app.models.base import utcnow
from app.models.models import (
    OPEN_STATUSES,
    Assignment,
    AssignmentStatus,
    AuditEvent,
    Estimate,
    EstimateStatus,
    MaterialUsage,
    OrganizationMembership,
    Priority,
    RequestStatus,
    ServiceCategory,
    ServiceRequest,
    SlaState,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianTimeOff,
    User,
)
from app.services import sla
from app.services.common import PageDep, count_rows, iso, page_body, request_ref

router = APIRouter()
R = ServiceRequest
_PLANNED = (AssignmentStatus.SCHEDULED, AssignmentStatus.ACCEPTED, AssignmentStatus.COMPLETED)
MAX_RANGE_DAYS = 366


def _bounds(ctx: Ctx, date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """[start, end) UTC instants for an inclusive organization-local date range."""
    if date_to < date_from:
        raise Unprocessable("date_to must not be before date_from.", code="RANGE_INVALID")
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        raise Unprocessable("Date range is limited to one year.", code="RANGE_TOO_LARGE")
    tz = ZoneInfo(ctx.org.timezone)
    return (
        datetime.combine(date_from, time(0), tz).astimezone(UTC),
        datetime.combine(date_to + timedelta(days=1), time(0), tz).astimezone(UTC),
    )


def _overlap_minutes(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    lo, hi = max(a0, b0), min(a1, b1)
    return int((hi - lo).total_seconds() // 60) if hi > lo else 0


async def _utilization(
    db: AsyncSession,
    ctx: Ctx,
    date_from: date,
    date_to: date,
    technician_id: uuid.UUID | None,
) -> dict[str, Any]:
    """planned assignment minutes / available working minutes, active technicians only.

    Available minutes are weekly availability inside the range minus recorded time off.
    Planned minutes are appointments in SCHEDULED, ACCEPTED, or COMPLETED state, clipped
    to the range. The percentage is not capped: appointments must fit inside availability
    and cannot overlap, so a value above 100% would indicate a data problem worth seeing.
    """
    start, end = _bounds(ctx, date_from, date_to)
    tz = ZoneInfo(ctx.org.timezone)
    query = (
        select(TechnicianProfile.id, User.full_name)
        .join(User, User.id == TechnicianProfile.user_id)
        .join(OrganizationMembership, OrganizationMembership.id == TechnicianProfile.membership_id)
        .where(
            TechnicianProfile.org_id == ctx.org_id,
            OrganizationMembership.is_active.is_(True),
            OrganizationMembership.role == "TECHNICIAN",
            User.is_active.is_(True),
        )
        .order_by(User.full_name)
    )
    if technician_id is not None:
        query = query.where(TechnicianProfile.id == technician_id)
    technicians = (await db.execute(query)).all()
    ids = [tech_id for tech_id, _ in technicians]
    available = dict.fromkeys(ids, 0)
    planned = dict.fromkeys(ids, 0)
    if ids:
        weekly: dict[uuid.UUID, dict[int, list[tuple[time, time]]]] = {i: {} for i in ids}
        for slot in await db.scalars(
            select(TechnicianAvailability).where(TechnicianAvailability.technician_id.in_(ids))
        ):
            weekly[slot.technician_id].setdefault(slot.weekday, []).append(
                (slot.starts_at, slot.ends_at)
            )
        time_off: dict[uuid.UUID, list[tuple[datetime, datetime]]] = {i: [] for i in ids}
        for off in await db.scalars(
            select(TechnicianTimeOff).where(
                TechnicianTimeOff.technician_id.in_(ids),
                TechnicianTimeOff.start_at < end,
                TechnicianTimeOff.end_at > start,
            )
        ):
            time_off[off.technician_id].append((off.start_at, off.end_at))
        day = date_from
        while day <= date_to:
            for tech_id in ids:
                for begins, ends in weekly[tech_id].get(day.weekday(), []):
                    w0 = datetime.combine(day, begins, tz)
                    w1 = datetime.combine(day, ends, tz)
                    minutes = int((w1 - w0).total_seconds() // 60)
                    minutes -= sum(_overlap_minutes(w0, w1, o0, o1) for o0, o1 in time_off[tech_id])
                    available[tech_id] += max(minutes, 0)
            day += timedelta(days=1)
        for assignment in await db.scalars(
            select(Assignment).where(
                Assignment.technician_id.in_(ids),
                Assignment.status.in_(_PLANNED),
                Assignment.start_at < end,
                Assignment.end_at > start,
            )
        ):
            planned[assignment.technician_id] += _overlap_minutes(
                assignment.start_at, assignment.end_at, start, end
            )

    def percent(p: int, a: int) -> float | None:
        return round(p * 100 / a, 1) if a > 0 else None

    total_planned, total_available = sum(planned.values()), sum(available.values())
    return {
        "planned_minutes": total_planned,
        "available_minutes": total_available,
        "utilization_percent": percent(total_planned, total_available),
        "technicians": [
            {
                "technician_id": str(tech_id),
                "full_name": name,
                "planned_minutes": planned[tech_id],
                "available_minutes": available[tech_id],
                "utilization_percent": percent(planned[tech_id], available[tech_id]),
            }
            for tech_id, name in technicians
        ],
    }


@router.get("/reports/dashboard", tags=["reports"], summary="Operational dashboard (staff)")
async def dashboard(
    ctx: StaffCtx,
    db: DB,
    date_from: Annotated[
        date | None, Query(description="Organization-local; default 13 days ago")
    ] = None,
    date_to: Annotated[date | None, Query(description="Organization-local; default today")] = None,
    category_id: uuid.UUID | None = None,
    technician_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    now = utcnow()
    tz = ZoneInfo(ctx.org.timezone)
    today = now.astimezone(tz).date()
    date_to = date_to or today
    date_from = date_from or (date_to - timedelta(days=13))
    start, end = _bounds(ctx, date_from, date_to)

    filters = [R.org_id == ctx.org_id]
    if category_id is not None:
        filters.append(R.category_id == category_id)
    if technician_id is not None:
        filters.append(
            exists(
                select(Assignment.id).where(
                    Assignment.request_id == R.id,
                    Assignment.technician_id == technician_id,
                    Assignment.status.in_(_PLANNED),
                )
            )
        )

    status_rows = await db.execute(
        select(R.status, func.count()).where(*filters).group_by(R.status)
    )
    status_counts = {status.value: 0 for status in RequestStatus}
    status_counts.update({status: count for status, count in status_rows})
    open_count = sum(status_counts[s.value] for s in OPEN_STATUSES)

    state = sla.sla_state_expr(now)
    sla_rows = await db.execute(
        select(state, func.count()).where(*filters, R.status.in_(OPEN_STATUSES)).group_by(state)
    )
    sla_counts = {s.value: 0 for s in SlaState}
    sla_counts.update({s: count for s, count in sla_rows})

    completed_in_range = await db.scalar(
        select(func.count())
        .select_from(R)
        .where(*filters, R.completed_at >= start, R.completed_at < end)
    )
    created_in_range = await db.scalar(
        select(func.count())
        .select_from(R)
        .where(*filters, R.created_at >= start, R.created_at < end)
    )

    upcoming_filters = [
        Assignment.org_id == ctx.org_id,
        Assignment.is_active,
        Assignment.start_at >= now,
        Assignment.start_at < now + timedelta(days=7),
    ]
    if technician_id is not None:
        upcoming_filters.append(Assignment.technician_id == technician_id)
    upcoming_query = (
        select(Assignment, R.number, R.title, User.full_name)
        .join(R, R.id == Assignment.request_id)
        .join(TechnicianProfile, TechnicianProfile.id == Assignment.technician_id)
        .join(User, User.id == TechnicianProfile.user_id)
        .where(*upcoming_filters)
    )
    if category_id is not None:
        upcoming_query = upcoming_query.where(R.category_id == category_id)
    upcoming_total = await count_rows(db, upcoming_query)
    upcoming_rows = await db.execute(upcoming_query.order_by(Assignment.start_at).limit(8))

    # Daily series: always the 14 organization-local days ending at date_to (REPORT-02).
    series_from = date_to - timedelta(days=13)
    series_start, series_end = _bounds(ctx, series_from, date_to)

    def bucket(instants: list[datetime | None]) -> dict[date, int]:
        counts: dict[date, int] = {}
        for instant in instants:
            if instant is None:
                continue
            day = instant.astimezone(tz).date()
            counts[day] = counts.get(day, 0) + 1
        return counts

    created_by_day = bucket(
        list(
            await db.scalars(
                select(R.created_at).where(
                    *filters, R.created_at >= series_start, R.created_at < series_end
                )
            )
        )
    )
    completed_by_day = bucket(
        list(
            await db.scalars(
                select(R.completed_at).where(
                    *filters, R.completed_at >= series_start, R.completed_at < series_end
                )
            )
        )
    )
    daily = [
        {
            "date": (series_from + timedelta(days=offset)).isoformat(),
            "new": created_by_day.get(series_from + timedelta(days=offset), 0),
            "completed": completed_by_day.get(series_from + timedelta(days=offset), 0),
        }
        for offset in range(14)
    ]

    in_range = [*filters, R.created_at >= start, R.created_at < end]
    priority_rows = dict(
        (await db.execute(select(R.priority, func.count()).where(*in_range).group_by(R.priority)))
        .tuples()
        .all()
    )
    category_rows = await db.execute(
        select(ServiceCategory.name, func.count())
        .join(R, R.category_id == ServiceCategory.id)
        .where(*in_range)
        .group_by(ServiceCategory.name)
        .order_by(func.count().desc(), ServiceCategory.name)
    )

    estimate_filters = [
        Estimate.org_id == ctx.org_id,
        Estimate.status == EstimateStatus.APPROVED,
        Estimate.decided_at >= start,
        Estimate.decided_at < end,
    ]
    usage_filters = [
        MaterialUsage.org_id == ctx.org_id,
        MaterialUsage.created_at >= start,
        MaterialUsage.created_at < end,
    ]
    if category_id is not None or technician_id is not None:
        scoped = select(R.id).where(*filters)
        estimate_filters.append(Estimate.request_id.in_(scoped))
        usage_filters.append(MaterialUsage.request_id.in_(scoped))
    approved = (
        await db.execute(
            select(func.coalesce(func.sum(Estimate.total_minor), 0), func.count()).where(
                *estimate_filters
            )
        )
    ).one()
    usage = (
        await db.execute(
            select(func.coalesce(func.sum(MaterialUsage.total_minor), 0), func.count()).where(
                *usage_filters
            )
        )
    ).one()

    return {
        "range": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "timezone": ctx.org.timezone,
        },
        "generated_at": iso(now),
        "status_counts": status_counts,
        "open_count": open_count,
        "overdue_count": sla_counts[SlaState.OVERDUE.value],
        "at_risk_count": sla_counts[SlaState.AT_RISK.value],
        "sla_counts_open": sla_counts,
        "created_in_range": created_in_range or 0,
        "completed_in_range": completed_in_range or 0,
        "upcoming_appointments": {
            "window_days": 7,
            "count": upcoming_total,
            "next": [
                {
                    "request_id": str(a.request_id),
                    "reference": request_ref(number),
                    "title": title,
                    "technician_name": tech_name,
                    "start_at": iso(a.start_at),
                    "end_at": iso(a.end_at),
                }
                for a, number, title, tech_name in upcoming_rows
            ],
        },
        "daily": {
            "date_from": series_from.isoformat(),
            "date_to": date_to.isoformat(),
            "unit": "requests per day",
            "series": daily,
        },
        "priority_distribution": [
            {"priority": p.value, "count": priority_rows.get(p.value, 0)} for p in Priority
        ],
        "category_distribution": [
            {"category": name, "count": count} for name, count in category_rows
        ],
        "utilization": await _utilization(db, ctx, date_from, date_to, technician_id),
        "financials": {
            "currency": ctx.org.currency,
            "approved_estimates_total_minor": int(approved[0]),
            "approved_estimates_count": approved[1],
            "material_usage_total_minor": int(usage[0]),
            "material_usage_count": usage[1],
            "note": "Approved estimates are estimates, not collected revenue.",
        },
    }


@router.get("/schedule", tags=["schedule"], summary="Appointments and availability for a board")
async def schedule(
    ctx: CurrentCtx,
    db: DB,
    date_from: date,
    date_to: date,
    technician_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    if ctx.is_requester:
        raise Forbidden("Requesters cannot view the schedule.", code="ROLE_FORBIDDEN")
    if (date_to - date_from).days > 31:
        raise Unprocessable("The schedule range is limited to 31 days.", code="RANGE_TOO_LARGE")
    start, end = _bounds(ctx, date_from, date_to)
    tech_query = (
        select(TechnicianProfile, User.full_name, OrganizationMembership.is_active)
        .join(User, User.id == TechnicianProfile.user_id)
        .join(OrganizationMembership, OrganizationMembership.id == TechnicianProfile.membership_id)
        .where(TechnicianProfile.org_id == ctx.org_id, OrganizationMembership.role == "TECHNICIAN")
        .order_by(User.full_name)
    )
    if ctx.is_technician:
        # A technician only ever sees their own calendar.
        tech_query = tech_query.where(TechnicianProfile.user_id == ctx.user.id)
    elif technician_id is not None:
        tech_query = tech_query.where(TechnicianProfile.id == technician_id)
    technicians = (await db.execute(tech_query)).all()
    ids = [profile.id for profile, _, _ in technicians]

    availability: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ids}
    time_off: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ids}
    appointments: list[dict[str, Any]] = []
    if ids:
        for slot in await db.scalars(
            select(TechnicianAvailability)
            .where(TechnicianAvailability.technician_id.in_(ids))
            .order_by(TechnicianAvailability.weekday, TechnicianAvailability.starts_at)
        ):
            availability[slot.technician_id].append(
                {
                    "weekday": slot.weekday,
                    "starts_at": slot.starts_at.strftime("%H:%M"),
                    "ends_at": slot.ends_at.strftime("%H:%M"),
                }
            )
        for off in await db.scalars(
            select(TechnicianTimeOff).where(
                TechnicianTimeOff.technician_id.in_(ids),
                TechnicianTimeOff.start_at < end,
                TechnicianTimeOff.end_at > start,
            )
        ):
            time_off[off.technician_id].append(
                {"start_at": iso(off.start_at), "end_at": iso(off.end_at), "reason": off.reason}
            )
        rows = await db.execute(
            select(Assignment, R.number, R.title, R.status, R.priority)
            .join(R, R.id == Assignment.request_id)
            .where(
                Assignment.technician_id.in_(ids),
                Assignment.status.in_(_PLANNED),
                Assignment.start_at < end,
                Assignment.end_at > start,
            )
            .order_by(Assignment.start_at)
            .limit(2000)
        )
        for assignment, number, title, status, priority in rows:
            appointments.append(
                {
                    "assignment_id": str(assignment.id),
                    "technician_id": str(assignment.technician_id),
                    "request_id": str(assignment.request_id),
                    "reference": request_ref(number),
                    "title": title,
                    "request_status": status,
                    "priority": priority,
                    "assignment_status": assignment.status,
                    "is_active": assignment.is_active,
                    "start_at": iso(assignment.start_at),
                    "end_at": iso(assignment.end_at),
                }
            )
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "timezone": ctx.org.timezone,
        "technicians": [
            {
                "id": str(profile.id),
                "full_name": name,
                "is_active": active,
                "availability": availability[profile.id],
                "time_off": time_off[profile.id],
            }
            for profile, name, active in technicians
        ],
        "appointments": appointments,
    }


@router.get("/audit", tags=["audit"], summary="Immutable organization audit timeline (admin)")
async def audit_timeline(
    ctx: AdminCtx,
    db: DB,
    page: PageDep,
    action: Annotated[str | None, Query(max_length=60, description="Prefix, e.g. 'staff.'")] = None,
    actor_id: uuid.UUID | None = None,
    request_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    query = (
        select(AuditEvent, User.full_name)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.org_id == ctx.org_id)
    )
    if action:
        query = query.where(AuditEvent.action.startswith(action, autoescape=True))
    if actor_id is not None:
        query = query.where(AuditEvent.actor_id == actor_id)
    if request_id is not None:
        query = query.where(AuditEvent.request_id == request_id)
    tz = ZoneInfo(ctx.org.timezone)
    if date_from is not None:
        query = query.where(AuditEvent.created_at >= datetime.combine(date_from, time(0), tz))
    if date_to is not None:
        query = query.where(
            AuditEvent.created_at < datetime.combine(date_to + timedelta(days=1), time(0), tz)
        )
    total = await count_rows(db, query)
    rows = await db.execute(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return page_body(
        [
            {
                "id": str(event.id),
                "action": event.action,
                "summary": event.summary,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "actor_name": actor or "System",
                "target_type": event.target_type,
                "target_id": str(event.target_id) if event.target_id else None,
                "request_id": str(event.request_id) if event.request_id else None,
                "before": event.before,
                "after": event.after,
                "created_at": iso(event.created_at),
            }
            for event, actor in rows
        ],
        total,
        page,
    )
