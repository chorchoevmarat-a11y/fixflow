import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import (
    auth,
    catalog,
    estimates,
    health,
    inventory,
    maintenance,
    notes,
    notifications,
    organizations,
    reports,
    requests,
    stream,
)
from app.config import settings
from app.core.errors import AppError, error_body
from app.core.logging import configure_logging, log, request_id_var
from app.database import SessionLocal, engine
from app.models.base import utcnow
from app.services.escalation import escalate_overdue
from app.services.events import hub

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

SLA_CHECK_INTERVAL_SECONDS = 60


async def _sla_loop() -> None:
    """In-process scheduler. Safe with many workers: escalation is an atomic UPDATE."""
    while True:
        await asyncio.sleep(SLA_CHECK_INTERVAL_SECONDS)
        try:
            async with SessionLocal() as db:
                count = await escalate_overdue(db, utcnow())
                await db.commit()
            if count:
                log.info("sla escalation", extra={"fields": {"escalated": count}})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("sla escalation failed", exc_info=True)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    await hub.start()
    sla_task = asyncio.create_task(_sla_loop())
    yield
    sla_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sla_task
    await hub.stop()
    await engine.dispose()


TAGS = [
    {"name": "auth", "description": "Sign-in, sign-out, current user and memberships."},
    {"name": "organizations", "description": "Settings, business hours, holidays."},
    {"name": "staff", "description": "Members, roles, activation."},
    {"name": "skills", "description": "Skill catalog."},
    {"name": "technicians", "description": "Profiles, skills, availability, time off."},
    {"name": "categories", "description": "Service categories and required skills."},
    {"name": "properties", "description": "Service properties."},
    {"name": "assets", "description": "Equipment assets and service history."},
    {"name": "requests", "description": "Intake, queue, lifecycle, assignment."},
    {"name": "estimates", "description": "Estimate versions and approvals."},
    {"name": "inventory", "description": "Items, stock, material usage."},
    {"name": "maintenance", "description": "Preventive maintenance plans and generation."},
    {"name": "notes and files", "description": "Work notes and evidence images."},
    {"name": "notifications", "description": "Per-user in-app notifications."},
    {"name": "reports", "description": "Dashboard and reports."},
    {"name": "schedule", "description": "Technician schedule board."},
    {"name": "audit", "description": "Immutable audit timeline."},
    {"name": "live updates", "description": "Server-Sent Events."},
    {"name": "health", "description": "Liveness and readiness."},
]

app = FastAPI(
    title="FixFlow API",
    version="1.0.0",
    description=(
        "Field service operations platform. All endpoints live under `/api/v1`. "
        "Authenticate with `Authorization: Bearer <token>` and select the organization "
        "with `X-Organization-ID` on every protected call. Errors always have the shape "
        '`{"error": {"code", "message", "details?"}, "request_id"}`.'
    ),
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    openapi_tags=TAGS,
    lifespan=lifespan,
)


class RequestContextMiddleware:
    """Request id, structured access log, and a hard cap on request body size.

    Pure ASGI (not BaseHTTPMiddleware) so streaming responses are never buffered.
    """

    def __init__(self, asgi_app: Callable[[Scope, Receive, Send], Awaitable[None]]) -> None:
        self.app = asgi_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        incoming = headers.get("x-request-id", "")
        request_id = (
            incoming if 8 <= len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_holder = {"status": 500}
        is_upload = headers.get("content-type", "").startswith("multipart/form-data")
        limit = (
            settings.MAX_UPLOAD_BYTES + 256 * 1024 if is_upload else settings.MAX_JSON_BODY_BYTES
        )
        received = 0
        response_started = False

        async def too_large() -> None:
            body = JSONResponse(
                error_body("PAYLOAD_TOO_LARGE", "Request body is too large.", request_id),
                status_code=413,
                headers={"X-Request-ID": request_id},
            )
            status_holder["status"] = 413
            await body(scope, receive, send)

        declared = headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await too_large()
            request_id_var.reset(token)
            return

        if b"%00" in scope.get("query_string", b"").lower():
            # PostgreSQL cannot compare/store U+0000; refuse it up front (422, not a 500).
            rejected = JSONResponse(
                error_body(
                    "VALIDATION_ERROR",
                    "Query parameters must not contain NUL (U+0000) characters.",
                    request_id,
                ),
                status_code=422,
                headers={"X-Request-ID": request_id},
            )
            status_holder["status"] = 422
            await rejected(scope, receive, send)
            request_id_var.reset(token)
            return

        class _BodyTooLarge(Exception):
            pass

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_holder["status"] = message["status"]
                response_headers = message.setdefault("headers", [])
                present = {name.lower() for name, _ in response_headers}
                response_headers.append((b"x-request-id", request_id.encode("latin-1")))
                # Authenticated JSON must never be cached by browsers or proxies.
                if b"cache-control" not in present:
                    response_headers.append((b"cache-control", b"private, no-store"))
                if b"x-content-type-options" not in present:
                    response_headers.append((b"x-content-type-options", b"nosniff"))
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await too_large()
        finally:
            log.info(
                "request",
                extra={
                    "fields": {
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status": status_holder["status"],
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            request_id_var.reset(token)


app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,  # bearer tokens only; no cookies, so no CSRF surface
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Organization-ID",
        "Idempotency-Key",
        "X-Request-ID",
    ],
    expose_headers=["X-Request-ID", "Idempotency-Replayed"],
)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        error_body(exc.code, exc.message, _request_id(request), exc.details),
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"] if part != "body"),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        error_body(
            "VALIDATION_ERROR", "Some fields are invalid.", _request_id(request), {"fields": fields}
        ),
        status_code=422,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codes = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return JSONResponse(
        error_body(codes.get(exc.status_code, "HTTP_ERROR"), str(exc.detail), _request_id(request)),
        status_code=exc.status_code,
    )


@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # A database constraint refused the write. Details stay in the log, not the response.
    log.warning("constraint violation", exc_info=True)
    return JSONResponse(
        error_body(
            "CONSTRAINT_VIOLATION",
            "The change conflicts with existing data.",
            _request_id(request),
        ),
        status_code=409,
    )


@app.exception_handler(DBAPIError)
async def database_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    unavailable = isinstance(exc, OperationalError | InterfaceError) or exc.connection_invalidated
    log.error("database error", exc_info=True)
    return JSONResponse(
        error_body(
            "DATABASE_UNAVAILABLE" if unavailable else "INTERNAL_ERROR",
            "The service is temporarily unavailable. Nothing was saved; try again."
            if unavailable
            else "Unexpected error. Nothing was saved.",
            _request_id(request),
        ),
        status_code=503 if unavailable else 500,
    )


@app.exception_handler(OSError)
async def connection_error_handler(request: Request, exc: OSError) -> JSONResponse:
    # asyncpg raises plain OSError (connection refused) when PostgreSQL is down.
    log.error("i/o error", exc_info=True)
    return JSONResponse(
        error_body(
            "DATABASE_UNAVAILABLE",
            "The service is temporarily unavailable. Nothing was saved; try again.",
            _request_id(request),
        ),
        status_code=503,
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled error", exc_info=True)
    return JSONResponse(
        error_body("INTERNAL_ERROR", "Unexpected error. Nothing was saved.", _request_id(request)),
        status_code=500,
    )


for module in (
    health,
    auth,
    organizations,
    catalog,
    requests,
    estimates,
    inventory,
    notes,
    maintenance,
    notifications,
    reports,
    stream,
):
    app.include_router(module.router, prefix="/api/v1")
