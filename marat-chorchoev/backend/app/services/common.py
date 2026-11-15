"""Cross-cutting helpers: audit trail, notifications, calendars, pagination."""

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.models import (
    AuditEvent,
    BusinessHours,
    Holiday,
    Notification,
    Organization,
    OrganizationMembership,
    Role,
    User,
)
from app.services import events
from app.services.sla import Calendar


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def sid(value: uuid.UUID | None) -> str | None:
    return str(value) if value is not None else None


def request_ref(number: int) -> str:
    return f"REQ-{number:05d}"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Page:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=settings.MAX_PAGE_SIZE)] = settings.DEFAULT_PAGE_SIZE,
) -> Page:
    return Page(page=page, page_size=page_size)


PageDep = Annotated[Page, Depends(page_params)]


async def count_rows(db: AsyncSession, query: Any) -> int:
    total = await db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    return int(total or 0)


def page_body(items: Sequence[Any], total: int, page: Page) -> dict[str, Any]:
    return {
        "items": list(items),
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
        "total_pages": (total + page.page_size - 1) // page.page_size,
    }


# ---------------------------------------------------------------------------
# Audit and notifications
# ---------------------------------------------------------------------------


def audit(
    db: AsyncSession,
    *,
    org_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None,
    summary: str,
    request_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    is_public: bool = True,
) -> AuditEvent:
    """Add an audit entry to the current transaction (same commit as the change)."""
    event = AuditEvent(
        org_id=org_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        summary=summary[:500],
        before=before,
        after=after,
        is_public=is_public,
    )
    db.add(event)
    return event


async def notify(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    recipient_ids: Iterable[uuid.UUID],
    type: str,
    title: str,
    body: str = "",
    request_id: uuid.UUID | None = None,
    exclude: uuid.UUID | None = None,
) -> None:
    recipients = sorted({r for r in recipient_ids if r != exclude}, key=str)
    if not recipients:
        return
    for recipient in recipients:
        db.add(
            Notification(
                org_id=org_id,
                recipient_id=recipient,
                type=type,
                title=title[:200],
                body=body,
                request_id=request_id,
            )
        )
    await db.flush()
    await events.publish(db, org_id, "notification.created", user_ids=recipients, kind=type)


async def staff_user_ids(db: AsyncSession, org_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(OrganizationMembership.user_id)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(
            OrganizationMembership.org_id == org_id,
            OrganizationMembership.role.in_([Role.ADMIN, Role.DISPATCHER]),
            OrganizationMembership.is_active.is_(True),
            User.is_active.is_(True),
        )
    )
    return list(rows)


# ---------------------------------------------------------------------------
# Business calendar
# ---------------------------------------------------------------------------


async def load_calendar(db: AsyncSession, org: Organization) -> Calendar:
    hours: dict[int, list] = {}
    for row in await db.scalars(select(BusinessHours).where(BusinessHours.org_id == org.id)):
        hours.setdefault(row.weekday, []).append((row.opens_at, row.closes_at))
    holidays = await db.scalars(select(Holiday.day).where(Holiday.org_id == org.id))
    return Calendar(
        tz=ZoneInfo(org.timezone),
        hours={day: tuple(sorted(intervals)) for day, intervals in hours.items()},
        holidays=frozenset(holidays),
    )
