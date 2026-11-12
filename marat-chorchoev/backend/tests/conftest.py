import asyncio
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.models import (
    Asset,
    AssetStatus,
    InventoryItem,
    MemberRole,
    Organization,
    OrganizationMembership,
    Property,
    ServiceCategory,
    User,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def setup_test_data(db_session: AsyncSession):
    # Create Organization 1
    org1 = Organization(
        id=uuid.uuid4(),
        name="Apex FM",
        slug="apex-fm",
        timezone="America/New_York",
    )
    # Create Organization 2
    org2 = Organization(
        id=uuid.uuid4(),
        name="Beacon Services",
        slug="beacon-services",
        timezone="America/Chicago",
    )
    db_session.add_all([org1, org2])
    await db_session.flush()

    pwd = hash_password("secret123")
    user_owner = User(
        id=uuid.uuid4(),
        email="owner@apex.io",
        hashed_password=pwd,
        full_name="Alice Owner",
    )
    user_tech = User(
        id=uuid.uuid4(),
        email="tech@apex.io",
        hashed_password=pwd,
        full_name="Bob Tech",
    )
    user_client = User(
        id=uuid.uuid4(),
        email="client@apex.io",
        hashed_password=pwd,
        full_name="Charlie Client",
    )
    db_session.add_all([user_owner, user_tech, user_client])
    await db_session.flush()

    m_owner = OrganizationMembership(
        id=uuid.uuid4(),
        organization_id=org1.id,
        user_id=user_owner.id,
        role=MemberRole.OWNER,
    )
    m_tech = OrganizationMembership(
        id=uuid.uuid4(),
        organization_id=org1.id,
        user_id=user_tech.id,
        role=MemberRole.TECHNICIAN,
        hourly_rate=Decimal("50.00"),
        skills=["HVAC", "Plumbing"],
    )
    m_client = OrganizationMembership(
        id=uuid.uuid4(),
        organization_id=org1.id,
        user_id=user_client.id,
        role=MemberRole.CLIENT,
    )
    db_session.add_all([m_owner, m_tech, m_client])

    # Category, Property, Asset, Inventory for Org 1
    cat = ServiceCategory(
        id=uuid.uuid4(),
        organization_id=org1.id,
        name="HVAC",
        sla_hours=24.0,
    )
    prop = Property(
        id=uuid.uuid4(),
        organization_id=org1.id,
        name="Tower One",
        address="100 Wall St",
    )
    db_session.add_all([cat, prop])
    await db_session.flush()

    asset = Asset(
        id=uuid.uuid4(),
        organization_id=org1.id,
        property_id=prop.id,
        name="HVAC Rooftop unit 1",
        asset_tag="HVAC-01",
        status=AssetStatus.ACTIVE,
    )
    item = InventoryItem(
        id=uuid.uuid4(),
        organization_id=org1.id,
        name="Filter X",
        sku="FLT-X",
        unit="piece",
        unit_cost=Decimal("15.00"),
        stock_quantity=Decimal("100.000"),
    )
    db_session.add_all([asset, item])
    await db_session.commit()

    return {
        "org1": org1,
        "org2": org2,
        "owner": user_owner,
        "tech": user_tech,
        "client": user_client,
        "m_owner": m_owner,
        "m_tech": m_tech,
        "m_client": m_client,
        "category": cat,
        "property": prop,
        "asset": asset,
        "item": item,
    }


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    def _make_headers(user: User, org: Organization, role: MemberRole) -> dict[str, str]:
        token = create_access_token({
            "sub": str(user.id),
            "email": user.email,
            "org_id": str(org.id),
            "role": role.value,
        })
        return {
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": str(org.id),
        }
    return _make_headers
