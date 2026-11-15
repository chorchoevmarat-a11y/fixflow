"""Persistent idempotency for retryable commands (API-03).

Clients send an ``Idempotency-Key`` header. The key row is inserted in the same
transaction as the command, so:

* the first execution stores its response next to the key and commits both together;
* a replay with the same payload returns the stored response without re-executing;
* the same key with a different payload is rejected with 409;
* a failed command rolls its key row back, so the client may retry it;
* two concurrent deliveries are serialized by the unique index (the second insert
  waits for the first transaction to finish).

Keys live in PostgreSQL, so they survive restarts and are shared by all API workers.
"""

from typing import Annotated, Any

from fastapi import Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import Ctx
from app.core.errors import BadRequest, Conflict
from app.core.security import payload_hash
from app.models.models import IdempotencyKey

IdempotencyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        description="Client-generated unique key (8-100 chars). Replays return the original result.",
    ),
]


def _validate(key: str) -> str:
    key = key.strip()
    if not 8 <= len(key) <= 100:
        raise BadRequest(
            "Idempotency-Key must be 8-100 characters.", code="IDEMPOTENCY_KEY_INVALID"
        )
    return key


async def begin(
    db: AsyncSession, ctx: Ctx, scope: str, key: str | None, payload: Any
) -> JSONResponse | None:
    """Return the stored response for a replay, or None when the command must run."""
    if key is None:
        return None
    key = _validate(key)
    digest = payload_hash(payload)
    inserted = await db.scalar(
        insert(IdempotencyKey)
        .values(org_id=ctx.org_id, user_id=ctx.user.id, scope=scope, key=key, payload_hash=digest)
        .on_conflict_do_nothing(index_elements=["org_id", "user_id", "scope", "key"])
        .returning(IdempotencyKey.id)
    )
    if inserted is not None:
        return None
    existing = (
        await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.org_id == ctx.org_id,
                IdempotencyKey.user_id == ctx.user.id,
                IdempotencyKey.scope == scope,
                IdempotencyKey.key == key,
            )
        )
    ).scalar_one()
    if existing.payload_hash != digest:
        raise Conflict(
            "This Idempotency-Key was already used with a different payload.",
            code="IDEMPOTENCY_KEY_REUSED",
        )
    if existing.response_body is None or existing.response_status is None:
        raise Conflict("The original command is still in progress.", code="IDEMPOTENCY_IN_PROGRESS")
    return JSONResponse(
        existing.response_body,
        status_code=existing.response_status,
        headers={"Idempotency-Replayed": "true"},
    )


async def finish(
    db: AsyncSession, ctx: Ctx, scope: str, key: str | None, status_code: int, body: Any
) -> None:
    """Record the response; committed together with the command's own changes."""
    if key is None:
        return
    await db.execute(
        update(IdempotencyKey)
        .where(
            IdempotencyKey.org_id == ctx.org_id,
            IdempotencyKey.user_id == ctx.user.id,
            IdempotencyKey.scope == scope,
            IdempotencyKey.key == _validate(key),
        )
        .values(response_status=status_code, response_body=jsonable_encoder(body))
    )
