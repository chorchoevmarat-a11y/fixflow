"""Test harness.

Tests run against a real PostgreSQL database because the behaviour under test (row
locks, exclusion constraints, ON CONFLICT, deferred foreign keys) only exists there.

Provide the connection string through TEST_DATABASE_URL. As a guard against wiping
real data, the database name must end in ``_test``; the suite refuses to run otherwise.
"""

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from urllib.parse import urlsplit

import pytest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://fixflow:fixflow@localhost:5432/fixflow_test"
)
if TEST_DATABASE_URL.startswith("postgresql://"):
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_database = urlsplit(TEST_DATABASE_URL).path.lstrip("/")
if not _database.endswith("_test"):
    raise pytest.UsageError(
        f"Refusing to run: TEST_DATABASE_URL points at database '{_database}'. "
        "The test suite drops all tables, so the database name must end in '_test'."
    )

# Must be set before the application modules are imported.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="fixflow-test-uploads-")
os.environ["ENVIRONMENT"] = "test"

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.security import hash_password, hash_token  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import clock  # noqa: E402
from app.models.models import (  # noqa: E402
    Asset,
    AuthSession,
    BusinessHours,
    CategorySkill,
    InventoryItem,
    Organization,
    OrganizationMembership,
    Property,
    Role,
    ServiceCategory,
    Skill,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    User,
)

PASSWORD = "Test-Password-123"
_PASSWORD_HASH = hash_password(PASSWORD)


async def _reset_schema() -> None:
    admin = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with admin.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> Iterator[None]:
    """Build the schema from the real Alembic migrations (not create_all)."""
    from alembic.config import Config

    from alembic import command

    asyncio.run(_reset_schema())
    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "alembic")
    )
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def _real_clock() -> Iterator[None]:
    yield
    clock.release()


@dataclass
class Member:
    user_id: uuid.UUID
    email: str
    role: Role
    org_id: uuid.UUID
    membership_id: uuid.UUID
    token: str
    technician_id: uuid.UUID | None = None

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Organization-ID": str(self.org_id)}


@dataclass
class OrgFixture:
    id: uuid.UUID
    admin: Member
    dispatcher: Member
    requester: Member
    requester2: Member
    tech: Member
    tech2: Member
    category_id: uuid.UUID  # requires the "Electrical" skill
    open_category_id: uuid.UUID  # no required skills
    property_id: uuid.UUID
    asset_id: uuid.UUID
    item_id: uuid.UUID
    skill_id: uuid.UUID
    extra: dict[str, uuid.UUID] = field(default_factory=dict)


@dataclass
class World:
    a: OrgFixture
    b: OrgFixture
    client: httpx.AsyncClient

    async def call(self, member: Member, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {**member.headers, **kwargs.pop("headers", {})}
        return await self.client.request(method, f"/api/v1{path}", headers=headers, **kwargs)

    async def get(self, member: Member, path: str, **kwargs) -> httpx.Response:
        return await self.call(member, "GET", path, **kwargs)

    async def post(
        self, member: Member, path: str, json: dict | None = None, **kwargs
    ) -> httpx.Response:
        return await self.call(
            member, "POST", path, json=json if json is not None else {}, **kwargs
        )

    async def ok(self, member: Member, method: str, path: str, **kwargs) -> dict:
        response = await self.call(member, method, path, **kwargs)
        assert response.status_code < 300, (
            f"{method} {path} -> {response.status_code} {response.text}"
        )
        return response.json()


async def _build_org(db, slug: str) -> OrgFixture:
    org = Organization(name=f"Org {slug.upper()}", slug=f"org-{slug}", timezone="Asia/Bishkek")
    db.add(org)
    await db.flush()
    for weekday in range(5):
        db.add(BusinessHours(org_id=org.id, weekday=weekday, opens_at=time(9), closes_at=time(18)))
    skill = Skill(org_id=org.id, name="Electrical")
    db.add(skill)
    await db.flush()

    async def member(name: str, role: Role, with_skill: bool = True) -> Member:
        user = User(
            email=f"{name}@{slug}.example.com",
            full_name=f"{name.title()} {slug.upper()}",
            password_hash=_PASSWORD_HASH,
        )
        db.add(user)
        await db.flush()
        membership = OrganizationMembership(org_id=org.id, user_id=user.id, role=role)
        db.add(membership)
        await db.flush()
        token = f"test-{uuid.uuid4().hex}"
        db.add(
            AuthSession(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime(2100, 1, 1, tzinfo=UTC),
            )
        )
        technician_id = None
        if role == Role.TECHNICIAN:
            profile = TechnicianProfile(org_id=org.id, membership_id=membership.id, user_id=user.id)
            db.add(profile)
            await db.flush()
            technician_id = profile.id
            if with_skill:
                db.add(TechnicianSkill(org_id=org.id, technician_id=profile.id, skill_id=skill.id))
            for weekday in range(5):
                db.add(
                    TechnicianAvailability(
                        org_id=org.id,
                        technician_id=profile.id,
                        weekday=weekday,
                        starts_at=time(9),
                        ends_at=time(18),
                    )
                )
        return Member(user.id, user.email, role, org.id, membership.id, token, technician_id)

    admin = await member("admin", Role.ADMIN)
    dispatcher = await member("dispatcher", Role.DISPATCHER)
    requester = await member("requester", Role.REQUESTER)
    requester2 = await member("requester2", Role.REQUESTER)
    tech = await member("tech", Role.TECHNICIAN)
    tech2 = await member("tech2", Role.TECHNICIAN)

    category = ServiceCategory(org_id=org.id, name="Electrical repair", description="Wiring")
    open_category = ServiceCategory(org_id=org.id, name="General", description="Anything")
    prop = Property(org_id=org.id, name="Main Tower", address=f"1 {slug.upper()} Street, Bishkek")
    db.add_all([category, open_category, prop])
    await db.flush()
    db.add(CategorySkill(org_id=org.id, category_id=category.id, skill_id=skill.id))
    asset = Asset(
        org_id=org.id, property_id=prop.id, code="AHU-001", name="Air handler", asset_type="HVAC"
    )
    item = InventoryItem(
        org_id=org.id,
        code="FLT-1",
        name="Filter",
        unit="pcs",
        stock_quantity=10,
        reorder_threshold=3,
        unit_price_minor=85000,
    )
    db.add_all([asset, item])
    await db.flush()
    return OrgFixture(
        id=org.id,
        admin=admin,
        dispatcher=dispatcher,
        requester=requester,
        requester2=requester2,
        tech=tech,
        tech2=tech2,
        category_id=category.id,
        open_category_id=open_category.id,
        property_id=prop.id,
        asset_id=asset.id,
        item_id=item.id,
        skill_id=skill.id,
    )


@pytest_asyncio.fixture
async def world() -> AsyncGenerator[World]:
    """Two fully separate organizations and an in-process HTTP client."""
    async with engine.begin() as connection:
        tables = await connection.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        )
        names = ", ".join(f'"{name}"' for name in tables)
        await connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    async with SessionLocal() as db:
        org_a = await _build_org(db, "a")
        org_b = await _build_org(db, "b")
        await db.commit()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield World(a=org_a, b=org_b, client=client)
