"""
Deterministic seed script for FixFlow database.
Creates test organizations, users, properties, assets, categories, inventory, and sample requests.
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.database import AsyncSessionLocal, engine
from app.models.base import Base
from app.models.models import (
    Asset,
    AssetStatus,
    InventoryItem,
    MemberRole,
    Organization,
    OrganizationMembership,
    Property,
    RecurrenceRule,
    RequestPriority,
    RequestStatus,
    ServiceCategory,
    ServiceRequest,
    User,
)


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        existing_org = await session.execute(select(Organization).limit(1))
        if existing_org.scalar_one_or_none():
            print("[Seed] Database already seeded.")
            return

        print("[Seed] Seeding database with initial data...")

        # 1. Users
        password_hash = hash_password("password123")

        admin_user = User(
            email="admin@fixflow.io",
            hashed_password=password_hash,
            full_name="Alice Admin",
            is_superuser=True,
        )
        tech_user = User(
            email="tech@fixflow.io",
            hashed_password=password_hash,
            full_name="Bob Technician",
        )
        client_user = User(
            email="client@fixflow.io",
            hashed_password=password_hash,
            full_name="Charlie Client",
        )
        session.add_all([admin_user, tech_user, client_user])
        await session.flush()

        # 2. Organization 1
        org1 = Organization(
            name="Apex Facilities Management",
            slug="apex-fm",
            timezone="America/New_York",
            business_hours={"mon-fri": "08:00-18:00"},
            sla_policy={"emergency": 4, "urgent": 8, "high": 24, "medium": 48, "low": 120},
        )
        # Organization 2 (for multi-tenant isolation testing)
        org2 = Organization(
            name="Beacon Property Services",
            slug="beacon-ps",
            timezone="America/Chicago",
        )
        session.add_all([org1, org2])
        await session.flush()

        # 3. Memberships
        m1 = OrganizationMembership(
            organization_id=org1.id,
            user_id=admin_user.id,
            role=MemberRole.OWNER,
        )
        m2 = OrganizationMembership(
            organization_id=org1.id,
            user_id=tech_user.id,
            role=MemberRole.TECHNICIAN,
            hourly_rate=Decimal("65.00"),
            skills=["HVAC", "Electrical", "Plumbing"],
        )
        m3 = OrganizationMembership(
            organization_id=org1.id,
            user_id=client_user.id,
            role=MemberRole.CLIENT,
        )
        # Org 2 membership
        m4 = OrganizationMembership(
            organization_id=org2.id,
            user_id=admin_user.id,
            role=MemberRole.VIEWER,
        )
        session.add_all([m1, m2, m3, m4])
        await session.flush()

        # 4. Categories
        cat_hvac = ServiceCategory(
            organization_id=org1.id,
            name="HVAC",
            description="Heating, ventilation, and air conditioning",
            sla_hours=24.0,
            color="#3B82F6",
        )
        cat_plumbing = ServiceCategory(
            organization_id=org1.id,
            name="Plumbing",
            description="Pipes, leaks, drainage",
            sla_hours=12.0,
            color="#10B981",
        )
        session.add_all([cat_hvac, cat_plumbing])
        await session.flush()

        # 5. Properties
        prop1 = Property(
            organization_id=org1.id,
            name="Grandview Towers",
            address="100 Grand Ave",
            city="New York",
            state="NY",
            postal_code="10001",
            contact_name="Front Desk",
            contact_phone="555-0100",
        )
        prop2 = Property(
            organization_id=org1.id,
            name="Midtown Logistics Center",
            address="500 5th Ave",
            city="New York",
            state="NY",
            postal_code="10018",
            contact_name="Warehouse Mgr",
            contact_phone="555-0200",
        )
        session.add_all([prop1, prop2])
        await session.flush()

        # 6. Assets
        asset1 = Asset(
            organization_id=org1.id,
            property_id=prop1.id,
            name="Chiller Unit Roof #1",
            asset_tag="HVAC-CHILL-001",
            make="Carrier",
            model="AquaForce 30XA",
            serial_number="CAR-9938210",
            status=AssetStatus.ACTIVE,
            year=2021,
        )
        asset2 = Asset(
            organization_id=org1.id,
            property_id=prop2.id,
            name="Boiler System B-2",
            asset_tag="BLR-002",
            make="Burnham",
            model="Series 2",
            serial_number="BRN-448190",
            status=AssetStatus.ACTIVE,
            year=2019,
        )
        session.add_all([asset1, asset2])
        await session.flush()

        # 7. Inventory Items
        inv1 = InventoryItem(
            organization_id=org1.id,
            name="HEPA Air Filter 24x24x2",
            sku="FLT-HEPA-2424",
            unit="piece",
            unit_cost=Decimal("28.50"),
            stock_quantity=Decimal("50.000"),
            min_stock_level=Decimal("10.000"),
            location="Shelf A-3",
        )
        inv2 = InventoryItem(
            organization_id=org1.id,
            name="2-Inch Copper Pipe Coupling",
            sku="PLM-COP-020",
            unit="piece",
            unit_cost=Decimal("6.75"),
            stock_quantity=Decimal("120.000"),
            min_stock_level=Decimal("25.000"),
            location="Bin C-12",
        )
        session.add_all([inv1, inv2])
        await session.flush()

        # 8. Sample Service Requests
        sr1 = ServiceRequest(
            org_id=org1.id,
            requester_id=client_user.id,
            property_id=prop1.id,
            asset_id=asset1.id,
            category_id=cat_hvac.id,
            request_number="REQ-2026-0001",
            title="Chiller making grinding noise on floor 14",
            description="Loud grinding sound reported since this morning. Ambient temp rising.",
            priority=RequestPriority.HIGH,
            status=RequestStatus.SUBMITTED,
        )
        sr2 = ServiceRequest(
            org_id=org1.id,
            requester_id=client_user.id,
            property_id=prop2.id,
            category_id=cat_plumbing.id,
            request_number="REQ-2026-0002",
            title="Minor water leak in basement storage area",
            description="Slow drip under the main water distribution riser.",
            priority=RequestPriority.MEDIUM,
            status=RequestStatus.SUBMITTED,
        )
        session.add_all([sr1, sr2])

        await session.commit()
        print("[Seed] Seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
