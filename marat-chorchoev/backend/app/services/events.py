"""Organization-scoped live updates over PostgreSQL LISTEN/NOTIFY.

``publish`` issues ``pg_notify`` inside the caller's transaction, so an event is
delivered only if (and when) the change commits. Every API worker holds one listening
connection and fans events out to its own Server-Sent-Events subscribers, which keeps
live updates correct with any number of workers and no extra broker.

Events are hints, not state: clients re-fetch canonical data when one arrives and
after every reconnect (API-06).
"""

import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.logging import log

CHANNEL = "fixflow_events"
_QUEUE_SIZE = 200


@dataclass(eq=False, slots=True)
class Subscriber:
    org_id: str
    user_id: str
    is_staff: bool
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_QUEUE_SIZE)
    )

    def wants(self, event: dict[str, Any]) -> bool:
        if event.get("org_id") != self.org_id:
            return False
        audience = event.get("audience") or {}
        if self.is_staff and audience.get("staff"):
            return True
        return self.user_id in (audience.get("user_ids") or [])

    def offer(self, event: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # Slow consumer: drop the backlog and tell it to reload canonical state.
            while not self.queue.empty():
                self.queue.get_nowait()
            self.queue.put_nowait({"type": "resync"})


class EventHub:
    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()

    def subscribe(
        self, org_id: uuid.UUID | str, user_id: uuid.UUID | str, is_staff: bool
    ) -> Subscriber:
        subscriber = Subscriber(org_id=str(org_id), user_id=str(user_id), is_staff=is_staff)
        self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)

    def _dispatch(self, payload: str) -> None:
        try:
            event = json.loads(payload)
        except ValueError:
            return
        public = {k: v for k, v in event.items() if k != "audience"}
        for subscriber in list(self._subscribers):
            if subscriber.wants(event):
                subscriber.offer(public)

    def _on_notify(self, _conn: Any, _pid: int, _channel: str, payload: str) -> None:
        self._dispatch(payload)

    async def _run(self) -> None:
        dsn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        while True:
            conn: asyncpg.Connection | None = None
            try:
                conn = await asyncpg.connect(dsn)
                await conn.add_listener(CHANNEL, self._on_notify)
                self._ready.set()
                # Anything published while we were disconnected is lost: force a re-fetch.
                for subscriber in list(self._subscribers):
                    subscriber.offer({"type": "resync"})
                while not conn.is_closed():
                    await asyncio.sleep(2)
                    await conn.execute("SELECT 1")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.warning("event listener disconnected; retrying", exc_info=True)
            finally:
                self._ready.clear()
                if conn is not None and not conn.is_closed():
                    with contextlib.suppress(Exception):
                        await conn.close()
            await asyncio.sleep(1)

    async def start(self, wait: bool = False) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())
        if wait:
            await asyncio.wait_for(self._ready.wait(), timeout=10)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


hub = EventHub()


async def publish(
    db: AsyncSession,
    org_id: uuid.UUID,
    event_type: str,
    *,
    staff: bool = False,
    user_ids: list[uuid.UUID] | tuple[uuid.UUID, ...] = (),
    **data: Any,
) -> None:
    """Queue an event for delivery when the surrounding transaction commits."""
    payload = {
        "type": event_type,
        "org_id": str(org_id),
        "audience": {"staff": staff, "user_ids": sorted({str(u) for u in user_ids})},
        **{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in data.items()},
    }
    await db.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHANNEL, "payload": json.dumps(payload)},
    )
