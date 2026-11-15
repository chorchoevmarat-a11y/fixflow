from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.logging import log
from app.database import SessionLocal

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Liveness: the process is up")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness: PostgreSQL is reachable and migrated",
    responses={503: {"description": "Database unavailable or schema missing"}},
)
async def ready() -> JSONResponse:
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
            revision = await db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except Exception:
        log.warning("readiness check failed", exc_info=True)
        return JSONResponse({"status": "unavailable", "database": "down"}, status_code=503)
    if revision is None:
        return JSONResponse({"status": "unavailable", "database": "not migrated"}, status_code=503)
    return JSONResponse({"status": "ok", "database": "up", "schema_revision": revision})
