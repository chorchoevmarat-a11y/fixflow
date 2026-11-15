"""Technician eligibility for an appointment slot (SCHED-01..05).

``evaluate`` answers, for every technician of an organization, whether they can take a
slot and — if not — exactly why. The dispatcher's candidate list and the server-side
assignment guard both use it, so the UI can never disagree with enforcement.
"""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Unprocessable
from app.models.models import (
    Assignment,
    CategorySkill,
    Organization,
    OrganizationMembership,
    ServiceRequest,
    Skill,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    TechnicianTimeOff,
    User,
)
from app.services.common import iso, request_ref

MIN_APPOINTMENT = timedelta(minutes=30)
MAX_SCHEDULE_HORIZON = timedelta(days=730)


def validate_slot(start_at: datetime, end_at: datetime, now: datetime) -> None:
    """Shape rules that do not depend on the technician (SCHED-02)."""
    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise Unprocessable("Appointment times must include a UTC offset.", code="SLOT_INVALID")
    if end_at <= start_at:
        raise Unprocessable("Appointment must end after it starts.", code="SLOT_INVALID")
    if end_at - start_at < MIN_APPOINTMENT:
        raise Unprocessable("Appointment must last at least 30 minutes.", code="SLOT_TOO_SHORT")
    if start_at < now:
        raise Unprocessable("Appointment cannot start in the past.", code="SLOT_IN_PAST")
    # Far-future instants (e.g. year 9999) overflow calendar arithmetic downstream (500) and are
    # never a real appointment.
    if end_at > now + MAX_SCHEDULE_HORIZON:
        raise Unprocessable("Appointment must be within the next two years.", code="SLOT_TOO_FAR")


def _merge(intervals: list[tuple[time, time]]) -> list[tuple[time, time]]:
    merged: list[tuple[time, time]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def within_availability(
    tz: ZoneInfo, weekly: dict[int, list[tuple[time, time]]], start_at: datetime, end_at: datetime
) -> bool:
    """The slot must sit inside one continuous working interval on its local day."""
    local_start = start_at.astimezone(tz)
    local_end = end_at.astimezone(tz)
    if local_start.date() != local_end.date():
        return False
    for begins, ends in _merge(weekly.get(local_start.weekday(), [])):
        if begins <= local_start.time() and local_end.time() <= ends:
            return True
    return False


async def evaluate(
    db: AsyncSession,
    org: Organization,
    *,
    category_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    technician_ids: list[uuid.UUID] | None = None,
    exclude_request_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    tz = ZoneInfo(org.timezone)
    profile_query = (
        select(TechnicianProfile, User, OrganizationMembership)
        .join(User, User.id == TechnicianProfile.user_id)
        .join(OrganizationMembership, OrganizationMembership.id == TechnicianProfile.membership_id)
        .where(TechnicianProfile.org_id == org.id)
        .order_by(User.full_name)
    )
    if technician_ids is not None:
        profile_query = profile_query.where(TechnicianProfile.id.in_(technician_ids))
    profiles = (await db.execute(profile_query)).all()
    ids = [profile.id for profile, _, _ in profiles]
    if not ids:
        return []

    required = dict(
        (
            await db.execute(
                select(Skill.id, Skill.name)
                .join(CategorySkill, CategorySkill.skill_id == Skill.id)
                .where(CategorySkill.category_id == category_id, CategorySkill.org_id == org.id)
            )
        )
        .tuples()
        .all()
    )
    skills: dict[uuid.UUID, dict[uuid.UUID, str]] = {i: {} for i in ids}
    for tech_id, skill_id, name in await db.execute(
        select(TechnicianSkill.technician_id, Skill.id, Skill.name)
        .join(Skill, Skill.id == TechnicianSkill.skill_id)
        .where(TechnicianSkill.technician_id.in_(ids))
    ):
        skills[tech_id][skill_id] = name

    weekly: dict[uuid.UUID, dict[int, list[tuple[time, time]]]] = {i: {} for i in ids}
    for row in await db.scalars(
        select(TechnicianAvailability).where(TechnicianAvailability.technician_id.in_(ids))
    ):
        weekly[row.technician_id].setdefault(row.weekday, []).append((row.starts_at, row.ends_at))

    time_off: dict[uuid.UUID, list[TechnicianTimeOff]] = {i: [] for i in ids}
    for row in await db.scalars(
        select(TechnicianTimeOff).where(
            TechnicianTimeOff.technician_id.in_(ids),
            TechnicianTimeOff.start_at < end_at,
            TechnicianTimeOff.end_at > start_at,
        )
    ):
        time_off[row.technician_id].append(row)

    # Workload window: the local calendar week (Mon-Sun) containing the slot.
    local_day = start_at.astimezone(tz).date()
    week_start = datetime.combine(local_day - timedelta(days=local_day.weekday()), time(0), tz)
    week_end = week_start + timedelta(days=7)
    day_start = datetime.combine(local_day, time(0), tz)
    day_end = day_start + timedelta(days=1)

    conflicts: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ids}
    workload = {i: {"day_minutes": 0, "week_minutes": 0, "week_jobs": 0} for i in ids}
    busy_query = (
        select(Assignment, ServiceRequest.number, ServiceRequest.title)
        .join(ServiceRequest, ServiceRequest.id == Assignment.request_id)
        .where(
            Assignment.technician_id.in_(ids),
            Assignment.is_active,
            Assignment.start_at < week_end.astimezone(UTC),
            Assignment.end_at > week_start.astimezone(UTC),
        )
    )
    for assignment, number, title in await db.execute(busy_query):
        if exclude_request_id is not None and assignment.request_id == exclude_request_id:
            continue
        minutes = int((assignment.end_at - assignment.start_at).total_seconds() // 60)
        load = workload[assignment.technician_id]
        load["week_minutes"] += minutes
        load["week_jobs"] += 1
        if assignment.start_at < day_end and assignment.end_at > day_start:
            load["day_minutes"] += minutes
        # Half-open comparison: touching appointments do not conflict (SCHED-03).
        if assignment.start_at < end_at and assignment.end_at > start_at:
            conflicts[assignment.technician_id].append(
                {
                    "request_id": str(assignment.request_id),
                    "reference": request_ref(number),
                    "title": title,
                    "start_at": iso(assignment.start_at),
                    "end_at": iso(assignment.end_at),
                }
            )

    result: list[dict[str, Any]] = []
    for profile, user, membership in profiles:
        active = membership.is_active and user.is_active
        missing = sorted(name for sid_, name in required.items() if sid_ not in skills[profile.id])
        available = within_availability(tz, weekly[profile.id], start_at, end_at)
        reasons: list[dict[str, str]] = []
        if not active:
            reasons.append({"code": "INACTIVE", "message": "Technician is deactivated."})
        if missing:
            reasons.append(
                {"code": "MISSING_SKILLS", "message": "Missing skills: " + ", ".join(missing) + "."}
            )
        if not available:
            reasons.append(
                {
                    "code": "OUTSIDE_AVAILABILITY",
                    "message": "Slot is outside the technician's working hours.",
                }
            )
        if time_off[profile.id]:
            reasons.append({"code": "TIME_OFF", "message": "Technician has time off in this slot."})
        for conflict in conflicts[profile.id]:
            reasons.append(
                {
                    "code": "SCHEDULE_CONFLICT",
                    "message": f"Overlaps {conflict['reference']} ({conflict['title']}).",
                }
            )
        result.append(
            {
                "technician_id": str(profile.id),
                "user_id": str(user.id),
                "full_name": user.full_name,
                "title": profile.title,
                "is_active": active,
                "skills": sorted(skills[profile.id].values()),
                "required_skills": sorted(required.values()),
                "missing_skills": missing,
                "within_availability": available,
                "on_time_off": bool(time_off[profile.id]),
                "conflicts": conflicts[profile.id],
                "workload": workload[profile.id],
                "eligible": not reasons,
                "reasons": reasons,
            }
        )
    return result


async def suggest(
    db: AsyncSession,
    org: Organization,
    *,
    category_id: uuid.UUID,
    duration_minutes: int,
    now: datetime,
    preferred_start: datetime | None = None,
    limit: int = 6,
    horizon_days: int = 10,
) -> list[dict[str, Any]]:
    """Earliest bookable (technician, slot) options, best first (the "Smart slot finder").

    Candidate starts are on the hour in the organization's local time over the next
    ``horizon_days`` days. Every option is checked with the same ``evaluate`` rules that
    the assignment endpoint enforces, so a suggestion is always accepted when booked
    right away (barring someone else taking it first). A requester-preferred start is
    tried before anything else.
    """
    tz = ZoneInfo(org.timezone)
    duration = timedelta(minutes=max(30, duration_minutes))
    starts: list[datetime] = []
    if preferred_start is not None and preferred_start > now:
        starts.append(preferred_start)
    day = now.astimezone(tz).date()
    for offset in range(horizon_days):
        local_day = day + timedelta(days=offset)
        if local_day.weekday() >= 6:
            continue
        for hour in range(8, 20):
            start = datetime.combine(local_day, time(hour), tz).astimezone(UTC)
            if start > now and start not in starts:
                starts.append(start)

    options: list[dict[str, Any]] = []
    seen_technicians: dict[str, int] = {}
    for start in starts:
        end = start + duration
        for candidate in await evaluate(
            db, org, category_id=category_id, start_at=start, end_at=end
        ):
            if not candidate["eligible"]:
                continue
            tech_id = candidate["technician_id"]
            if seen_technicians.get(tech_id, 0) >= 2:
                continue  # keep the list varied: at most two options per technician
            seen_technicians[tech_id] = seen_technicians.get(tech_id, 0) + 1
            options.append(
                {
                    "technician_id": tech_id,
                    "technician_name": candidate["full_name"],
                    "start_at": iso(start),
                    "end_at": iso(end),
                    "week_minutes": candidate["workload"]["week_minutes"],
                    "matches_preference": preferred_start is not None and start == preferred_start,
                }
            )
        if len(options) >= limit * 3:
            break
    options.sort(key=lambda o: (not o["matches_preference"], o["start_at"], o["week_minutes"]))
    return options[:limit]
