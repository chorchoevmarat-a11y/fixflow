"""Organization settings, business calendar, staff, skills, and technician profiles."""

import uuid
from datetime import date, time
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Query
from pydantic import AwareDatetime, EmailStr, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import Body
from app.core.deps import DB, AdminCtx, Ctx, CurrentCtx, StaffCtx, TechnicianCtx
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.security import hash_password
from app.models.base import utcnow
from app.models.models import (
    Assignment,
    BusinessHours,
    Holiday,
    OrganizationMembership,
    Role,
    ServiceRequest,
    Skill,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    TechnicianTimeOff,
    User,
)
from app.services import sla
from app.services.common import PageDep, audit, count_rows, iso, load_calendar, page_body

router = APIRouter(tags=["organizations"])

# ---------------------------------------------------------------------------
# Organization settings and business calendar
# ---------------------------------------------------------------------------


class OrganizationPatch(Body):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("must be a valid IANA timezone, e.g. Asia/Bishkek") from exc
        return value


class HoursInterval(Body):
    weekday: int = Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")
    opens_at: time
    closes_at: time


class BusinessHoursBody(Body):
    intervals: list[HoursInterval] = Field(max_length=28)


class HolidayBody(Body):
    day: date
    name: str = Field(min_length=2, max_length=200)


async def _organization_view(db: AsyncSession, ctx: Ctx) -> dict[str, Any]:
    hours = await db.scalars(
        select(BusinessHours)
        .where(BusinessHours.org_id == ctx.org_id)
        .order_by(BusinessHours.weekday, BusinessHours.opens_at)
    )
    holidays = await db.scalars(
        select(Holiday).where(Holiday.org_id == ctx.org_id).order_by(Holiday.day)
    )
    return {
        "id": str(ctx.org.id),
        "name": ctx.org.name,
        "slug": ctx.org.slug,
        "timezone": ctx.org.timezone,
        "currency": ctx.org.currency,
        "business_hours": [
            {
                "weekday": h.weekday,
                "opens_at": h.opens_at.strftime("%H:%M"),
                "closes_at": h.closes_at.strftime("%H:%M"),
            }
            for h in hours
        ],
        "holidays": [{"id": str(h.id), "day": h.day.isoformat(), "name": h.name} for h in holidays],
        "sla_policy_hours": dict(sla.SLA_BUDGET_HOURS),
    }


async def _recalculate_open_slas(db: AsyncSession, ctx: Ctx, old: sla.Calendar) -> None:
    """Calendar changed: re-plan every running SLA clock in this organization."""
    await db.flush()
    new = await load_calendar(db, ctx.org)
    now = utcnow()
    running = await db.scalars(
        select(ServiceRequest)
        .where(
            ServiceRequest.org_id == ctx.org_id,
            ServiceRequest.sla_stopped_at.is_(None),
            ServiceRequest.sla_running_since.is_not(None),
        )
        .with_for_update()
    )
    for req in running:
        event = sla.recalculate(req, old, new, now)
        if event is not None:
            db.add(event)


@router.get("/organization", summary="Settings of the selected organization")
async def get_organization(ctx: CurrentCtx, db: DB) -> dict[str, Any]:
    return await _organization_view(db, ctx)


@router.patch("/organization", summary="Update name or timezone (admin)")
async def update_organization(body: OrganizationPatch, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    old_calendar = await load_calendar(db, ctx.org)
    before = {"name": ctx.org.name, "timezone": ctx.org.timezone}
    if body.name is not None:
        ctx.org.name = body.name
    if body.timezone is not None:
        ctx.org.timezone = body.timezone
    after = {"name": ctx.org.name, "timezone": ctx.org.timezone}
    if after != before:
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="organization.updated",
            target_type="organization",
            target_id=ctx.org_id,
            summary="Organization settings updated",
            before=before,
            after=after,
        )
        await _recalculate_open_slas(db, ctx, old_calendar)
    await db.commit()
    return await _organization_view(db, ctx)


@router.put("/organization/business-hours", summary="Replace weekly business hours (admin)")
async def replace_business_hours(body: BusinessHoursBody, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    by_day: dict[int, list[HoursInterval]] = {}
    for interval in body.intervals:
        if interval.closes_at <= interval.opens_at:
            raise Unprocessable("Closing time must be after opening time.", code="HOURS_INVALID")
        by_day.setdefault(interval.weekday, []).append(interval)
    for intervals in by_day.values():
        intervals.sort(key=lambda i: i.opens_at)
        for previous, current in zip(intervals, intervals[1:], strict=False):
            if current.opens_at < previous.closes_at:
                raise Unprocessable(
                    "Intervals on the same day must not overlap.", code="HOURS_OVERLAP"
                )

    old_calendar = await load_calendar(db, ctx.org)
    before = [
        f"{day}:{o:%H:%M}-{c:%H:%M}"
        for day, spans in sorted(old_calendar.hours.items())
        for o, c in spans
    ]
    await db.execute(delete(BusinessHours).where(BusinessHours.org_id == ctx.org_id))
    for interval in body.intervals:
        db.add(
            BusinessHours(
                org_id=ctx.org_id,
                weekday=interval.weekday,
                opens_at=interval.opens_at,
                closes_at=interval.closes_at,
            )
        )
    after = [
        f"{i.weekday}:{i.opens_at:%H:%M}-{i.closes_at:%H:%M}"
        for i in sorted(body.intervals, key=lambda i: (i.weekday, i.opens_at))
    ]
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="organization.business_hours_changed",
        target_type="organization",
        target_id=ctx.org_id,
        summary="Business hours changed",
        before={"intervals": before},
        after={"intervals": after},
    )
    await _recalculate_open_slas(db, ctx, old_calendar)
    await db.commit()
    return await _organization_view(db, ctx)


@router.post("/organization/holidays", status_code=201, summary="Add a holiday (admin)")
async def add_holiday(body: HolidayBody, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    exists_already = await db.scalar(
        select(Holiday.id).where(Holiday.org_id == ctx.org_id, Holiday.day == body.day)
    )
    if exists_already:
        raise Conflict("That date is already a holiday.", code="HOLIDAY_EXISTS")
    old_calendar = await load_calendar(db, ctx.org)
    holiday = Holiday(org_id=ctx.org_id, day=body.day, name=body.name)
    db.add(holiday)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="organization.holiday_added",
        target_type="holiday",
        target_id=holiday.id,
        summary=f"Holiday added: {body.day.isoformat()} {body.name}",
        after={"day": body.day.isoformat(), "name": body.name},
    )
    await _recalculate_open_slas(db, ctx, old_calendar)
    await db.commit()
    return await _organization_view(db, ctx)


@router.delete("/organization/holidays/{holiday_id}", summary="Remove a holiday (admin)")
async def remove_holiday(holiday_id: uuid.UUID, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    holiday = (
        await db.execute(
            select(Holiday).where(Holiday.id == holiday_id, Holiday.org_id == ctx.org_id)
        )
    ).scalar_one_or_none()
    if holiday is None:
        raise NotFound("Holiday not found.")
    old_calendar = await load_calendar(db, ctx.org)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="organization.holiday_removed",
        target_type="holiday",
        target_id=holiday.id,
        summary=f"Holiday removed: {holiday.day.isoformat()} {holiday.name}",
        before={"day": holiday.day.isoformat(), "name": holiday.name},
    )
    await db.delete(holiday)
    await _recalculate_open_slas(db, ctx, old_calendar)
    await db.commit()
    return await _organization_view(db, ctx)


# ---------------------------------------------------------------------------
# Staff and roles
# ---------------------------------------------------------------------------


class StaffCreate(Body):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    role: Role


class StaffPatch(Body):
    role: Role | None = None
    is_active: bool | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=200)


def _staff_row(
    membership: OrganizationMembership, user: User, technician_id: uuid.UUID | None
) -> dict[str, Any]:
    return {
        "membership_id": str(membership.id),
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": membership.role,
        "is_active": membership.is_active and user.is_active,
        "technician_id": str(technician_id) if technician_id else None,
        "created_at": iso(membership.created_at),
    }


def _staff_query(ctx: Ctx) -> Any:
    return (
        select(OrganizationMembership, User, TechnicianProfile.id)
        .join(User, User.id == OrganizationMembership.user_id)
        .outerjoin(TechnicianProfile, TechnicianProfile.membership_id == OrganizationMembership.id)
        .where(OrganizationMembership.org_id == ctx.org_id)
    )


@router.get("/staff", tags=["staff"], summary="Members of the organization (staff)")
async def list_staff(
    ctx: StaffCtx,
    db: DB,
    page: PageDep,
    role: Role | None = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> dict[str, Any]:
    query = _staff_query(ctx)
    if role is not None:
        query = query.where(OrganizationMembership.role == role)
    if is_active is not None:
        query = query.where(OrganizationMembership.is_active.is_(is_active))
    if q:
        like = f"%{q}%"
        query = query.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    total = await count_rows(db, query)
    rows = await db.execute(
        query.order_by(User.full_name, User.id).offset(page.offset).limit(page.page_size)
    )
    return page_body([_staff_row(m, u, t) for m, u, t in rows], total, page)


async def _ensure_profile(db: AsyncSession, membership: OrganizationMembership) -> None:
    existing = await db.scalar(
        select(TechnicianProfile.id).where(TechnicianProfile.membership_id == membership.id)
    )
    if existing is None:
        db.add(
            TechnicianProfile(
                org_id=membership.org_id, membership_id=membership.id, user_id=membership.user_id
            )
        )


@router.post("/staff", tags=["staff"], status_code=201, summary="Add a member (admin)")
async def create_staff(body: StaffCreate, ctx: AdminCtx, db: DB) -> dict[str, Any]:
    email = body.email.lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(
            email=email, full_name=body.full_name, password_hash=hash_password(body.password)
        )
        db.add(user)
        await db.flush()
    elif await db.scalar(
        select(OrganizationMembership.id).where(
            OrganizationMembership.org_id == ctx.org_id, OrganizationMembership.user_id == user.id
        )
    ):
        raise Conflict("This person is already a member.", code="MEMBER_EXISTS")
    membership = OrganizationMembership(org_id=ctx.org_id, user_id=user.id, role=body.role)
    db.add(membership)
    await db.flush()
    if body.role == Role.TECHNICIAN:
        await _ensure_profile(db, membership)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="staff.added",
        target_type="membership",
        target_id=membership.id,
        summary=f"{user.full_name} added as {body.role.value}",
        after={"email": email, "role": body.role.value},
    )
    await db.commit()
    row = (
        await db.execute(_staff_query(ctx).where(OrganizationMembership.id == membership.id))
    ).one()
    return _staff_row(*row)


@router.patch("/staff/{membership_id}", tags=["staff"], summary="Change role or activation (admin)")
async def update_staff(
    membership_id: uuid.UUID, body: StaffPatch, ctx: AdminCtx, db: DB
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.id == membership_id,
                OrganizationMembership.org_id == ctx.org_id,
            )
            .with_for_update(of=OrganizationMembership)
        )
    ).first()
    if row is None:
        raise NotFound("Member not found.")
    membership, user = row
    is_self = membership.id == ctx.membership.id
    if is_self and (
        (body.role is not None and body.role != membership.role) or body.is_active is False
    ):
        # Prevents self-elevation tricks and locking the organization out of its admin.
        raise Forbidden(
            "You cannot change your own role or deactivate yourself.", code="SELF_MODIFICATION"
        )

    if body.full_name is not None and body.full_name != user.full_name:
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="staff.renamed",
            target_type="membership",
            target_id=membership.id,
            summary=f"{user.full_name} renamed to {body.full_name}",
            before={"full_name": user.full_name},
            after={"full_name": body.full_name},
        )
        user.full_name = body.full_name

    if body.role is not None and body.role != membership.role:
        if membership.role == Role.TECHNICIAN:
            busy = await db.scalar(
                select(func.count())
                .select_from(Assignment)
                .join(TechnicianProfile, TechnicianProfile.id == Assignment.technician_id)
                .where(TechnicianProfile.membership_id == membership.id, Assignment.is_active)
            )
            if busy:
                raise Conflict(
                    "Unassign this technician's active jobs before changing the role.",
                    code="TECHNICIAN_HAS_ACTIVE_JOBS",
                )
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="staff.role_changed",
            target_type="membership",
            target_id=membership.id,
            summary=f"{user.full_name}: role {membership.role} -> {body.role.value}",
            before={"role": membership.role},
            after={"role": body.role.value},
        )
        membership.role = body.role
        if body.role == Role.TECHNICIAN:
            await _ensure_profile(db, membership)

    if body.is_active is not None and body.is_active != membership.is_active:
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="staff.activated" if body.is_active else "staff.deactivated",
            target_type="membership",
            target_id=membership.id,
            summary=f"{user.full_name} {'activated' if body.is_active else 'deactivated'}",
            before={"is_active": membership.is_active},
            after={"is_active": body.is_active},
        )
        membership.is_active = body.is_active

    await db.commit()
    fresh = (
        await db.execute(_staff_query(ctx).where(OrganizationMembership.id == membership.id))
    ).one()
    return _staff_row(*fresh)


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


class SkillBody(Body):
    name: str = Field(min_length=2, max_length=100)


@router.get("/skills", tags=["skills"], summary="Skill catalog")
async def list_skills(ctx: CurrentCtx, db: DB) -> list[dict[str, str]]:
    skills = await db.scalars(select(Skill).where(Skill.org_id == ctx.org_id).order_by(Skill.name))
    return [{"id": str(s.id), "name": s.name} for s in skills]


@router.post("/skills", tags=["skills"], status_code=201, summary="Create a skill (admin)")
async def create_skill(body: SkillBody, ctx: AdminCtx, db: DB) -> dict[str, str]:
    duplicate = await db.scalar(
        select(Skill.id).where(
            Skill.org_id == ctx.org_id, func.lower(Skill.name) == body.name.lower()
        )
    )
    if duplicate:
        raise Conflict("A skill with this name already exists.", code="SKILL_EXISTS")
    skill = Skill(org_id=ctx.org_id, name=body.name)
    db.add(skill)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="skill.created",
        target_type="skill",
        target_id=skill.id,
        summary=f"Skill created: {body.name}",
        after={"name": body.name},
    )
    await db.commit()
    return {"id": str(skill.id), "name": skill.name}


@router.delete("/skills/{skill_id}", tags=["skills"], summary="Delete a skill (admin)")
async def delete_skill(skill_id: uuid.UUID, ctx: AdminCtx, db: DB) -> dict[str, str]:
    skill = (
        await db.execute(select(Skill).where(Skill.id == skill_id, Skill.org_id == ctx.org_id))
    ).scalar_one_or_none()
    if skill is None:
        raise NotFound("Skill not found.")
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="skill.deleted",
        target_type="skill",
        target_id=skill.id,
        summary=f"Skill deleted: {skill.name}",
        before={"name": skill.name},
    )
    await db.delete(skill)
    await db.commit()
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Technician profiles, availability, time off
# ---------------------------------------------------------------------------


class AvailabilityInterval(Body):
    weekday: int = Field(ge=0, le=6)
    starts_at: time
    ends_at: time


class TechnicianUpdate(Body):
    title: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    skill_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    availability: list[AvailabilityInterval] | None = Field(default=None, max_length=28)


class TimeOffBody(Body):
    start_at: AwareDatetime
    end_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=300)


async def _technician_views(
    db: AsyncSession, org_id: uuid.UUID, where: Any = None, with_time_off: bool = False
) -> list[dict[str, Any]]:
    query = (
        select(TechnicianProfile, User, OrganizationMembership)
        .join(User, User.id == TechnicianProfile.user_id)
        .join(OrganizationMembership, OrganizationMembership.id == TechnicianProfile.membership_id)
        .where(TechnicianProfile.org_id == org_id, OrganizationMembership.role == Role.TECHNICIAN)
        .order_by(User.full_name)
    )
    if where is not None:
        query = query.where(where)
    rows = (await db.execute(query)).all()
    ids = [profile.id for profile, _, _ in rows]
    skills: dict[uuid.UUID, list[dict[str, str]]] = {i: [] for i in ids}
    availability: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ids}
    time_off: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ids}
    if ids:
        for tech_id, skill_id, name in await db.execute(
            select(TechnicianSkill.technician_id, Skill.id, Skill.name)
            .join(Skill, Skill.id == TechnicianSkill.skill_id)
            .where(TechnicianSkill.technician_id.in_(ids))
            .order_by(Skill.name)
        ):
            skills[tech_id].append({"id": str(skill_id), "name": name})
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
        if with_time_off:
            for off in await db.scalars(
                select(TechnicianTimeOff)
                .where(
                    TechnicianTimeOff.technician_id.in_(ids), TechnicianTimeOff.end_at > utcnow()
                )
                .order_by(TechnicianTimeOff.start_at)
                .limit(200)
            ):
                time_off[off.technician_id].append(
                    {
                        "id": str(off.id),
                        "start_at": iso(off.start_at),
                        "end_at": iso(off.end_at),
                        "reason": off.reason,
                    }
                )
    return [
        {
            "id": str(profile.id),
            "user_id": str(user.id),
            "membership_id": str(membership.id),
            "full_name": user.full_name,
            "email": user.email,
            "title": profile.title,
            "phone": profile.phone,
            "is_active": membership.is_active and user.is_active,
            "skills": skills[profile.id],
            "availability": availability[profile.id],
            "time_off": time_off[profile.id],
        }
        for profile, user, membership in rows
    ]


async def _get_profile(db: AsyncSession, ctx: Ctx, technician_id: uuid.UUID) -> TechnicianProfile:
    profile = (
        await db.execute(
            select(TechnicianProfile).where(
                TechnicianProfile.id == technician_id, TechnicianProfile.org_id == ctx.org_id
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        raise NotFound("Technician not found.", code="TECHNICIAN_NOT_FOUND")
    return profile


@router.get("/technicians", tags=["technicians"], summary="Technicians with skills and hours")
async def list_technicians(ctx: StaffCtx, db: DB) -> list[dict[str, Any]]:
    return await _technician_views(db, ctx.org_id, with_time_off=True)


@router.get("/technicians/me", tags=["technicians"], summary="The signed-in technician's profile")
async def my_technician_profile(ctx: TechnicianCtx, db: DB) -> dict[str, Any]:
    views = await _technician_views(
        db, ctx.org_id, TechnicianProfile.user_id == ctx.user.id, with_time_off=True
    )
    if not views:
        raise NotFound("Technician profile not found.", code="TECHNICIAN_NOT_FOUND")
    return views[0]


@router.put(
    "/technicians/{technician_id}",
    tags=["technicians"],
    summary="Update profile, skills, and weekly availability (admin)",
)
async def update_technician(
    technician_id: uuid.UUID, body: TechnicianUpdate, ctx: AdminCtx, db: DB
) -> dict[str, Any]:
    profile = await _get_profile(db, ctx, technician_id)
    changes: dict[str, Any] = {}
    if "title" in body.model_fields_set:
        profile.title = body.title
        changes["title"] = body.title
    if "phone" in body.model_fields_set:
        profile.phone = body.phone
        changes["phone"] = body.phone
    if body.skill_ids is not None:
        wanted = set(body.skill_ids)
        valid = set(
            await db.scalars(
                select(Skill.id).where(Skill.org_id == ctx.org_id, Skill.id.in_(wanted))
            )
        )
        if valid != wanted:
            # Includes ids from other organizations: never silently accepted.
            raise Unprocessable("Unknown skill id.", code="SKILL_NOT_FOUND")
        await db.execute(delete(TechnicianSkill).where(TechnicianSkill.technician_id == profile.id))
        for skill_id in sorted(wanted, key=str):
            db.add(TechnicianSkill(org_id=ctx.org_id, technician_id=profile.id, skill_id=skill_id))
        changes["skill_ids"] = sorted(str(s) for s in wanted)
    if body.availability is not None:
        by_day: dict[int, list[AvailabilityInterval]] = {}
        for slot in body.availability:
            if slot.ends_at <= slot.starts_at:
                raise Unprocessable("Interval must end after it starts.", code="HOURS_INVALID")
            by_day.setdefault(slot.weekday, []).append(slot)
        for slots in by_day.values():
            slots.sort(key=lambda s: s.starts_at)
            for previous, current in zip(slots, slots[1:], strict=False):
                if current.starts_at < previous.ends_at:
                    raise Unprocessable("Intervals must not overlap.", code="HOURS_OVERLAP")
        await db.execute(
            delete(TechnicianAvailability).where(TechnicianAvailability.technician_id == profile.id)
        )
        for slot in body.availability:
            db.add(
                TechnicianAvailability(
                    org_id=ctx.org_id,
                    technician_id=profile.id,
                    weekday=slot.weekday,
                    starts_at=slot.starts_at,
                    ends_at=slot.ends_at,
                )
            )
        changes["availability"] = [
            f"{s.weekday}:{s.starts_at:%H:%M}-{s.ends_at:%H:%M}" for s in body.availability
        ]
    if changes:
        audit(
            db,
            org_id=ctx.org_id,
            actor_id=ctx.user.id,
            action="technician.updated",
            target_type="technician",
            target_id=profile.id,
            summary="Technician profile updated",
            after=changes,
        )
    await db.commit()
    return (
        await _technician_views(
            db, ctx.org_id, TechnicianProfile.id == profile.id, with_time_off=True
        )
    )[0]


@router.post(
    "/technicians/{technician_id}/time-off",
    tags=["technicians"],
    status_code=201,
    summary="Record dated time off (staff)",
)
async def add_time_off(
    technician_id: uuid.UUID, body: TimeOffBody, ctx: StaffCtx, db: DB
) -> dict[str, Any]:
    profile = await _get_profile(db, ctx, technician_id)
    if body.end_at <= body.start_at:
        raise Unprocessable("Time off must end after it starts.", code="INTERVAL_INVALID")
    overlapping = await db.scalar(
        select(func.count())
        .select_from(Assignment)
        .where(
            Assignment.technician_id == profile.id,
            Assignment.is_active,
            Assignment.start_at < body.end_at,
            Assignment.end_at > body.start_at,
        )
    )
    if overlapping:
        raise Conflict(
            "The technician has active jobs in this period. Reschedule them first.",
            code="TIME_OFF_CONFLICT",
            details={"active_assignments": overlapping},
        )
    entry = TechnicianTimeOff(
        org_id=ctx.org_id,
        technician_id=profile.id,
        start_at=body.start_at,
        end_at=body.end_at,
        reason=body.reason,
    )
    db.add(entry)
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="technician.time_off_added",
        target_type="technician",
        target_id=profile.id,
        summary="Time off recorded",
        after={"start_at": iso(body.start_at), "end_at": iso(body.end_at), "reason": body.reason},
    )
    await db.commit()
    return {
        "id": str(entry.id),
        "start_at": iso(entry.start_at),
        "end_at": iso(entry.end_at),
        "reason": entry.reason,
    }


@router.delete(
    "/technicians/{technician_id}/time-off/{time_off_id}",
    tags=["technicians"],
    summary="Remove time off (staff)",
)
async def remove_time_off(
    technician_id: uuid.UUID, time_off_id: uuid.UUID, ctx: StaffCtx, db: DB
) -> dict[str, str]:
    entry = (
        await db.execute(
            select(TechnicianTimeOff).where(
                TechnicianTimeOff.id == time_off_id,
                TechnicianTimeOff.technician_id == technician_id,
                TechnicianTimeOff.org_id == ctx.org_id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFound("Time off entry not found.")
    audit(
        db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="technician.time_off_removed",
        target_type="technician",
        target_id=technician_id,
        summary="Time off removed",
        before={"start_at": iso(entry.start_at), "end_at": iso(entry.end_at)},
    )
    await db.delete(entry)
    await db.commit()
    return {"status": "deleted"}
