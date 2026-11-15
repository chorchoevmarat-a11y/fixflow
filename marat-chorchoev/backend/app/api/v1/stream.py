"""Authenticated Server-Sent Events stream (API-06)."""

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Header, Request
from fastapi.responses import StreamingResponse

from app.core.deps import authenticate, bearer_token, resolve_membership
from app.core.errors import AppError
from app.database import SessionLocal
from app.models.models import Role
from app.services.events import hub

router = APIRouter(tags=["live updates"])

HEARTBEAT_SECONDS = 15
RECHECK_SECONDS = 60


def _frame(event: dict) -> str:
    return f"event: {event.get('type', 'message')}\ndata: {json.dumps(event)}\n\n"


@router.get(
    "/stream",
    summary="Live updates for the selected organization (text/event-stream)",
    description=(
        "Send the same `Authorization` and `X-Organization-ID` headers as any other call. "
        "Events carry ids only; clients re-fetch canonical state. A `ready` event is sent "
        "on connect and a `resync` event whenever events may have been missed — on both, "
        "re-fetch everything on screen."
    ),
    response_class=StreamingResponse,
)
async def stream(
    request: Request, x_organization_id: Annotated[str | None, Header()] = None
) -> StreamingResponse:
    token = bearer_token(request)

    async def authorize() -> tuple[str, str, bool]:
        # Short-lived session: the stream must not pin a pooled connection.
        async with SessionLocal() as db:
            user, _ = await authenticate(db, token)
            membership, org = await resolve_membership(db, user, x_organization_id)
            return str(org.id), str(user.id), membership.role in (Role.ADMIN, Role.DISPATCHER)

    org_id, user_id, is_staff = await authorize()
    await hub.start()

    async def events() -> AsyncGenerator[str]:
        subscriber = hub.subscribe(org_id, user_id, is_staff)
        loop = asyncio.get_running_loop()
        last_check = loop.time()
        try:
            yield _frame({"type": "ready"})
            while True:
                try:
                    event = await asyncio.wait_for(
                        subscriber.queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                    yield _frame(event)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                if await request.is_disconnected():
                    return
                if loop.time() - last_check >= RECHECK_SECONDS:
                    last_check = loop.time()
                    try:
                        # Session expiry, sign-out, and deactivation end the stream.
                        await authorize()
                    except AppError as exc:
                        yield _frame({"type": "unauthorized", "code": exc.code})
                        return
        finally:
            hub.unsubscribe(subscriber)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
