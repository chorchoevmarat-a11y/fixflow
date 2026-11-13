"""Operational commands. Run with ``uv run python -m app.cli <command>``.

migrate                       apply database migrations (alembic upgrade head)
seed                          load deterministic demo data (no-op when present)
sla-check                     detect overdue requests and create escalations (SLA-07)
generate-maintenance [--date YYYY-MM-DD]
                              generate due preventive-maintenance requests (PM-05)
wait-for-db                   block until PostgreSQL accepts connections
reset-db --yes-destroy-local-data
                              DESTRUCTIVE: drop every table, re-migrate, re-seed
race-assign / race-consume    development-only concurrency simulations (SEED-06)
"""

import argparse
import asyncio
import shutil
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select, text

from app.config import settings
from app.database import SessionLocal, engine
from app.models.models import Organization

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres", "host.docker.internal"}


def _alembic(*args: str) -> None:
    from alembic.config import main as alembic_main

    alembic_main(argv=list(args))


async def _wait_for_db(timeout_seconds: int = 60) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return
        except Exception as exc:
            if asyncio.get_running_loop().time() > deadline:
                raise SystemExit(f"database not reachable after {timeout_seconds}s") from exc
            await asyncio.sleep(1)
        finally:
            await engine.dispose()


async def _sla_check() -> None:
    from app.services.escalation import escalate_overdue

    async with SessionLocal() as db:
        count = await escalate_overdue(db, datetime.now(UTC))
        await db.commit()
    print(f"[sla-check] {count} request(s) newly escalated")
    await engine.dispose()


async def _generate_maintenance(as_of: date) -> None:
    from app.services.maintenance import generate

    total = 0
    async with SessionLocal() as db:
        organizations = list(await db.scalars(select(Organization).where(Organization.is_active)))
        for org in organizations:
            created = await generate(db, org, as_of)
            await db.commit()
            for row in created:
                print(
                    f"[maintenance] {org.slug}: {row['reference']} <- {row['plan_title']} ({row['occurrence_date']})"
                )
            total += len(created)
    print(f"[maintenance] as of {as_of.isoformat()}: {total} request(s) generated")
    await engine.dispose()


async def _seed() -> None:
    from app import seed

    await seed.run()
    await engine.dispose()


async def _drop_everything() -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def _reset(confirmed: bool, allow_nonlocal: bool) -> None:
    host = urlsplit(settings.DATABASE_URL.replace("+asyncpg", "")).hostname or ""
    if not confirmed:
        raise SystemExit(
            "reset-db DELETES ALL DATA. Re-run with --yes-destroy-local-data to confirm."
        )
    if host not in LOCAL_HOSTS and not allow_nonlocal:
        raise SystemExit(
            f"refusing to reset non-local database host '{host}'. "
            "Pass --allow-nonlocal only if you are certain."
        )
    print(f"[reset-db] dropping all tables on {host} ...")
    asyncio.run(_drop_everything())
    uploads = Path(settings.UPLOAD_DIR)
    if uploads.is_dir():
        for child in uploads.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink()
    _alembic("upgrade", "head")
    asyncio.run(_seed())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("seed")
    commands.add_parser("sla-check")
    commands.add_parser("wait-for-db")
    generate_parser = commands.add_parser("generate-maintenance")
    generate_parser.add_argument(
        "--date", type=date.fromisoformat, default=None, help="as-of date (default: today, UTC)"
    )
    reset_parser = commands.add_parser("reset-db")
    reset_parser.add_argument("--yes-destroy-local-data", action="store_true")
    reset_parser.add_argument("--allow-nonlocal", action="store_true")
    for name in ("race-assign", "race-consume"):
        race = commands.add_parser(name)
        race.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    if args.command == "migrate":
        _alembic("upgrade", "head")
    elif args.command == "seed":
        asyncio.run(_seed())
    elif args.command == "sla-check":
        asyncio.run(_sla_check())
    elif args.command == "wait-for-db":
        asyncio.run(_wait_for_db())
    elif args.command == "generate-maintenance":
        asyncio.run(_generate_maintenance(args.date or datetime.now(UTC).date()))
    elif args.command == "reset-db":
        _reset(args.yes_destroy_local_data, args.allow_nonlocal)
    elif args.command in ("race-assign", "race-consume"):
        if not settings.is_development:
            raise SystemExit("race simulations are development-only (ENVIRONMENT=development)")
        from app import devtools

        asyncio.run(devtools.run(args.command, args.base_url))
    else:  # pragma: no cover
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
