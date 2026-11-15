"""Preventive-maintenance generation (PM-01..05).

Every occurrence of a plan becomes at most one service request. Uniqueness is enforced
by the ``uq_request_plan_occurrence`` constraint, and generation uses
``INSERT ... ON CONFLICT DO NOTHING`` against it, so re-runs and simultaneous workers
can never create a duplicate.
"""

import calendar
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.models import (
    Asset,
    AssetStatus,
    MaintenancePlan,
    Organization,
    Recurrence,
    RequestStatus,
    ServiceRequest,
)
from app.services import events, sla
from app.services.common import audit, load_calendar, request_ref

MAX_OCCURRENCES_PER_RUN = 60


def occurrence_dates(plan: MaintenancePlan) -> Iterator[date]:
    """Infinite, deterministic sequence of occurrence dates starting at ``first_date``."""
    first = plan.first_date
    index = 0
    while True:
        if plan.recurrence == Recurrence.WEEKLY:
            yield first + timedelta(weeks=index)
        else:
            month_index = first.month - 1 + index
            year = first.year + month_index // 12
            month = month_index % 12 + 1
            # Day-of-month is clamped (a plan on the 31st runs on the 30th / 28th).
            day = min(first.day, calendar.monthrange(year, month)[1])
            yield date(year, month, day)
        index += 1


async def _generated_dates(db: AsyncSession, plan_id: uuid.UUID) -> set[date]:
    rows = await db.scalars(
        select(ServiceRequest.occurrence_date).where(ServiceRequest.maintenance_plan_id == plan_id)
    )
    return {d for d in rows if d is not None}


async def next_occurrence(db: AsyncSession, plan: MaintenancePlan) -> date | None:
    """First occurrence that has not been generated yet (None when the plan is disabled)."""
    if not plan.is_enabled:
        return None
    done = await _generated_dates(db, plan.id)
    for index, day in enumerate(occurrence_dates(plan)):
        if day not in done:
            return day
        if index > 5000:
            break
    return None


async def generate(
    db: AsyncSession,
    org: Organization,
    as_of: date,
    *,
    plan_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Create requests for all occurrences due on or before ``as_of``. Caller commits."""
    query = (
        select(MaintenancePlan, Asset)
        .join(Asset, Asset.id == MaintenancePlan.asset_id)
        .where(
            MaintenancePlan.org_id == org.id,
            MaintenancePlan.is_enabled.is_(True),
            # PM-04: a retired asset stops generating.
            Asset.status == AssetStatus.ACTIVE,
            MaintenancePlan.first_date <= as_of,
        )
        .order_by(MaintenancePlan.created_at, MaintenancePlan.id)
    )
    if plan_id is not None:
        query = query.where(MaintenancePlan.id == plan_id)
    plans = (await db.execute(query)).all()
    if not plans:
        return []

    cal = await load_calendar(db, org)
    now = utcnow()
    created: list[dict[str, Any]] = []
    for plan, asset in plans:
        done = await _generated_dates(db, plan.id)
        due: list[date] = []
        for day in occurrence_dates(plan):
            if day > as_of or len(due) >= MAX_OCCURRENCES_PER_RUN:
                break
            if day not in done:
                due.append(day)
        for day in due:
            number = await db.scalar(
                update(Organization)
                .where(Organization.id == org.id)
                .values(next_request_number=Organization.next_request_number + 1)
                .returning(Organization.next_request_number - 1)
            )
            req = ServiceRequest(
                id=uuid.uuid4(),
                org_id=org.id,
                number=number,
                requester_id=plan.created_by_id,
                property_id=asset.property_id,
                asset_id=asset.id,
                category_id=plan.category_id,
                title=plan.title,
                description=plan.description,
                priority=plan.priority,
                status=RequestStatus.SUBMITTED,
                maintenance_plan_id=plan.id,
                occurrence_date=day,
                sla_budget_seconds=sla.budget_seconds_for(plan.priority),
                sla_consumed_seconds=0,
            )
            sla_event = sla.start(req, cal, now)
            values = {
                column.name: getattr(req, column.name)
                for column in ServiceRequest.__table__.columns
                if column.name not in ("created_at", "updated_at")
            }
            inserted = await db.scalar(
                insert(ServiceRequest)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_request_plan_occurrence")
                .returning(ServiceRequest.id)
            )
            if inserted is None:
                # Another worker generated this occurrence first.
                continue
            db.add(sla_event)
            audit(
                db,
                org_id=org.id,
                actor_id=actor_id,
                action="request.generated",
                target_type="service_request",
                target_id=req.id,
                request_id=req.id,
                summary=f"Generated from maintenance plan “{plan.title}” for {day.isoformat()}",
                after={
                    "status": RequestStatus.SUBMITTED.value,
                    "maintenance_plan_id": str(plan.id),
                    "occurrence_date": day.isoformat(),
                },
            )
            created.append(
                {
                    "request_id": str(req.id),
                    "reference": request_ref(number or 0),
                    "plan_id": str(plan.id),
                    "plan_title": plan.title,
                    "occurrence_date": day.isoformat(),
                }
            )
    if created:
        await db.flush()
        await events.publish(db, org.id, "request.updated", staff=True, action="generated")
    return created
