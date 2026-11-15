"""Overdue detection and one-time escalation (SLA-06 / SLA-07)."""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import OPEN_STATUSES, NotificationType, ServiceRequest, SlaState
from app.services import events, sla
from app.services.common import audit, notify, request_ref, staff_user_ids


async def escalate_overdue(db: AsyncSession, now: datetime) -> int:
    """Flag newly overdue requests and notify staff. Caller commits.

    The conditional UPDATE is the idempotency guard: ``sla_escalated_at`` flips from NULL
    exactly once per request, even when several schedulers run at the same moment, so a
    request can never be escalated twice.
    """
    rows = (
        await db.execute(
            update(ServiceRequest)
            .where(
                ServiceRequest.sla_escalated_at.is_(None),
                ServiceRequest.sla_stopped_at.is_(None),
                ServiceRequest.status.in_(OPEN_STATUSES),
                sla.sla_state_expr(now) == SlaState.OVERDUE.value,
            )
            .values(sla_escalated_at=now)
            .returning(
                ServiceRequest.id,
                ServiceRequest.org_id,
                ServiceRequest.number,
                ServiceRequest.title,
                ServiceRequest.requester_id,
            )
            .execution_options(synchronize_session=False)
        )
    ).all()
    recipients_by_org: dict = {}
    for request_id, org_id, number, title, _requester_id in rows:
        if org_id not in recipients_by_org:
            recipients_by_org[org_id] = await staff_user_ids(db, org_id)
        reference = request_ref(number)
        audit(
            db,
            org_id=org_id,
            actor_id=None,
            action="sla.escalated",
            target_type="service_request",
            target_id=request_id,
            request_id=request_id,
            summary=f"{reference} is overdue against its SLA and was escalated",
            is_public=False,
        )
        await notify(
            db,
            org_id=org_id,
            recipient_ids=recipients_by_org[org_id],
            type=NotificationType.SLA_OVERDUE,
            title=f"{reference} is overdue",
            body=f"“{title}” has exceeded its SLA budget.",
            request_id=request_id,
        )
        await events.publish(
            db, org_id, "request.updated", staff=True, request_id=request_id, action="escalated"
        )
    return len(rows)
