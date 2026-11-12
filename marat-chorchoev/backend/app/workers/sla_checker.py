import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.models import Notification, RequestStatus, ServiceRequest


async def check_sla_breaches() -> int:
    """Checks open service requests and marks them breached if past sla_due_at."""
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        query = select(ServiceRequest).where(
            ServiceRequest.sla_due_at < now,
            ServiceRequest.sla_breached == False,
            ServiceRequest.status.notin_([
                RequestStatus.COMPLETED,
                RequestStatus.CANCELLED,
                RequestStatus.CLOSED,
            ]),
        )
        res = await session.execute(query)
        breached_requests = res.scalars().all()

        for req in breached_requests:
            req.sla_breached = True
            # Create notification for requester
            if req.requester_id:
                notif = Notification(
                    user_id=req.requester_id,
                    org_id=req.org_id,
                    title="SLA Breached",
                    body=f"Service request {req.request_number} has breached its SLA deadline.",
                    type="sla_breach",
                    reference_type="service_request",
                    reference_id=req.id,
                )
                session.add(notif)

        await session.commit()
        return len(breached_requests)


async def run_sla_checker_loop(interval_seconds: int = 60):
    while True:
        try:
            count = await check_sla_breaches()
            if count > 0:
                print(f"[SLA Checker] Breached {count} requests")
        except Exception as e:
            print(f"[SLA Checker Error] {e}")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_sla_checker_loop())
