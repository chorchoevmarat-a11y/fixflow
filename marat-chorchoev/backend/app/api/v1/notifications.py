"""In-app notifications. Strictly scoped to (organization, recipient) (COMM-04)."""

import uuid
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select, update

from app.core.deps import DB, Ctx, CurrentCtx
from app.core.errors import NotFound
from app.models.base import utcnow
from app.models.models import Notification
from app.services import events
from app.services.common import PageDep, count_rows, iso, page_body

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _mine(ctx: Ctx) -> Any:
    return (Notification.org_id == ctx.org_id) & (Notification.recipient_id == ctx.user.id)


@router.get("", summary="My notifications in the selected organization")
async def list_notifications(
    ctx: CurrentCtx, db: DB, page: PageDep, unread_only: bool = False
) -> dict[str, Any]:
    query = select(Notification).where(_mine(ctx))
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    total = await count_rows(db, query)
    rows = await db.scalars(
        query.order_by(Notification.created_at.desc(), Notification.id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    body = page_body(
        [
            {
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "body": n.body,
                "request_id": str(n.request_id) if n.request_id else None,
                "created_at": iso(n.created_at),
                "read_at": iso(n.read_at),
            }
            for n in rows
        ],
        total,
        page,
    )
    body["unread_count"] = await _unread(db, ctx)
    return body


async def _unread(db: DB, ctx: Ctx) -> int:
    return int(
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(_mine(ctx), Notification.read_at.is_(None))
        )
        or 0
    )


@router.get("/unread-count", summary="Number of unread notifications")
async def unread_count(ctx: CurrentCtx, db: DB) -> dict[str, int]:
    return {"unread_count": await _unread(db, ctx)}


@router.post("/{notification_id}/read", summary="Mark one notification as read")
async def mark_read(notification_id: uuid.UUID, ctx: CurrentCtx, db: DB) -> dict[str, int]:
    found = await db.scalar(
        update(Notification)
        .where(Notification.id == notification_id, _mine(ctx))
        .values(read_at=func.coalesce(Notification.read_at, utcnow()))
        .returning(Notification.id)
    )
    if found is None:
        # Also the answer for another user's notification: existence is not disclosed.
        raise NotFound("Notification not found.", code="NOTIFICATION_NOT_FOUND")
    await events.publish(db, ctx.org_id, "notification.read", user_ids=[ctx.user.id])
    await db.commit()
    return {"unread_count": await _unread(db, ctx)}


@router.post("/read-all", summary="Mark all my notifications as read")
async def mark_all_read(ctx: CurrentCtx, db: DB) -> dict[str, int]:
    await db.execute(
        update(Notification)
        .where(_mine(ctx), Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    await events.publish(db, ctx.org_id, "notification.read", user_ids=[ctx.user.id])
    await db.commit()
    return {"unread_count": 0}
