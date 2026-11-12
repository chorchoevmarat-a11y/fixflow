import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.v1 import (
    assets,
    assignments,
    audit,
    auth,
    categories,
    estimates,
    files,
    health,
    inventory,
    maintenance,
    notes,
    notifications,
    organizations,
    properties,
    reports,
    requests,
    ws,
)
from app.config import settings
from app.database import engine
from app.models.base import Base

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables or run migrations
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        # In test or offline, continue
        pass
    yield
    # Shutdown
    await engine.dispose()


app = FastAPI(
    title="FixFlow API",
    version="0.1.0",
    description="FixFlow Field Service Operations Platform Backend",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Attach SlowAPI limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID and Timing Middleware
@app.middleware("http")
async def add_process_time_and_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start_time = time.time()

    # Max body size check (15MB)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 15 * 1024 * 1024:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "Request payload exceeds 15MB limit"},
        )

    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    response.headers["X-Request-ID"] = request_id
    return response


# Validation Error Handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        errors.append({
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors, "code": "VALIDATION_ERROR"},
    )


# Include Routers under /api/v1
api_v1_routers = [
    health.router,
    auth.router,
    organizations.router,
    properties.router,
    assets.router,
    categories.router,
    requests.router,
    assignments.router,
    estimates.router,
    inventory.router,
    maintenance.router,
    notes.router,
    files.router,
    notifications.router,
    reports.router,
    audit.router,
    ws.router,
]

for router in api_v1_routers:
    app.include_router(router, prefix="/api/v1")
