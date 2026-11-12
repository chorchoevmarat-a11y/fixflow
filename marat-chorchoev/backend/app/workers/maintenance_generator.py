import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.models import (
    MaintenancePlan,
    MaintenancePlanOccurrence,
    RecurrenceRule,
    RequestStatus,
    ServiceRequest,
)

RECURRENCE_DAYS = {
    RecurrenceRule.DAILY: 1,
    RecurrenceRule.WEEKLY: 7,
    RecurrenceRule.BIWEEKLY: 14,
    RecurrenceRule.MONTHLY: 30,
    RecurrenceRule.QUARTERLY: 90,
    RecurrenceRule.SEMI_ANNUAL: 180,
    RecurrenceRule.ANNUAL: 365,
}


async def generate_due_maintenance_plans() -> int:
    """Finds active plans whose next occurrence is within advance_days and creates service requests."""
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        query = select(MaintenancePlan).where(
            MaintenancePlan.is_active == True,
            MaintenancePlan.next_occurrence.is_not(None),
        )
        res = await session.execute(query)
        plans = res.scalars().all()

        generated_count = 0
        for plan in plans:
            advance_cutoff = now + timedelta(days=plan.advance_days)
            if plan.next_occurrence <= advance_cutoff:
                # Check occurrence idempotency
                occ_query = select(MaintenancePlanOccurrence).where(
                    MaintenancePlanOccurrence.plan_id == plan.id,
                    MaintenancePlanOccurrence.occurrence_date == plan.next_occurrence,
                )
                existing = (await session.execute(occ_query)).scalar_one_or_none()
                if not existing:
                    req_number = f"PM-{now.year}-{uuid.uuid4().hex[:6].upper()}"
                    sr = ServiceRequest(
                        org_id=plan.organization_id,
                        property_id=plan.property_id,
                        asset_id=plan.asset_id,
                        category_id=plan.category_id,
                        request_number=req_number,
                        title=f"Scheduled Maintenance: {plan.name}",
                        description=plan.description,
                        priority=plan.priority,
                        status=RequestStatus.SUBMITTED,
                        source="pm",
                        scheduled_start=plan.next_occurrence,
                    )
                    session.add(sr)
                    await session.flush()

                    occ = MaintenancePlanOccurrence(
                        plan_id=plan.id,
                        service_request_id=sr.id,
                        occurrence_date=plan.next_occurrence,
                    )
                    session.add(occ)

                    days = RECURRENCE_DAYS.get(plan.recurrence, 30)
                    plan.last_generated_at = now
                    plan.next_occurrence = plan.next_occurrence + timedelta(days=days)
                    generated_count += 1

        await session.commit()
        return generated_count


async def run_maintenance_generator_loop(interval_seconds: int = 300):
    while True:
        try:
            count = await generate_due_maintenance_plans()
            if count > 0:
                print(f"[PM Generator] Generated {count} PM service requests")
        except Exception as e:
            print(f"[PM Generator Error] {e}")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_maintenance_generator_loop())
