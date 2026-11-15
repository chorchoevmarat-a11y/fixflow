"""Deterministic, disposable demonstration data (SEED-01..04).

Reference data (organizations, accounts, catalog) is inserted directly with fixed
UUIDs. Operational history (requests, assignments, estimates, materials, evidence,
feedback, maintenance) is then *replayed through the real HTTP API* with a pinned
clock, so every seeded record went through the same validation, SLA, audit, and
notification code paths as live data.

Re-running the seed is a no-op once the demo organizations exist.

ALL ACCOUNTS HERE ARE DISPOSABLE DEMO ACCOUNTS. Never use these credentials elsewhere.
"""

import io
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, hash_token
from app.database import SessionLocal
from app.models.base import clock
from app.models.models import (
    Asset,
    AssetStatus,
    AuthSession,
    BusinessHours,
    CategorySkill,
    InventoryItem,
    Organization,
    OrganizationMembership,
    Property,
    PropertyRequester,
    Role,
    ServiceCategory,
    Skill,
    TechnicianAvailability,
    TechnicianProfile,
    TechnicianSkill,
    TechnicianTimeOff,
    User,
)
from app.services.escalation import escalate_overdue

DEMO_PASSWORD = "FixFlow-Demo-2026!"  # demo-only, documented in README
NAMESPACE = uuid.UUID("f1f10f10-0000-4000-8000-000000000001")
TZ = ZoneInfo("Asia/Bishkek")
SLOT_HOURS = (9, 11, 14, 16)  # two-hour appointments inside 09:00-18:00


def sid(key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, key)


# ---------------------------------------------------------------------------
# Reference data definitions
# ---------------------------------------------------------------------------

ORGS = {
    "a": ("Salymbekov University Facilities", "salymbekov"),
    "b": ("Salymbekov University Hospital", "salymbekov-hospital"),
}

# email, full name, [(org, role)]
USERS: list[tuple[str, str, list[tuple[str, Role]]]] = [
    ("admin@salymbekov.example.com", "Aigul Asanova", [("a", Role.ADMIN)]),
    ("dispatcher@salymbekov.example.com", "Bakyt Dzhumabaev", [("a", Role.DISPATCHER)]),
    ("requester1@salymbekov.example.com", "Cholpon Ismailova", [("a", Role.REQUESTER)]),
    ("requester2@salymbekov.example.com", "Daniyar Kasymov", [("a", Role.REQUESTER)]),
    ("requester3@salymbekov.example.com", "Elnura Toktosunova", [("a", Role.REQUESTER)]),
    ("requester4@salymbekov.example.com", "Azamat Kurmanov", [("a", Role.REQUESTER)]),
    ("tech1@salymbekov.example.com", "Farid Abdyldaev", [("a", Role.TECHNICIAN)]),
    ("tech2@salymbekov.example.com", "Gulnara Sadykova", [("a", Role.TECHNICIAN)]),
    ("tech3@salymbekov.example.com", "Ilyas Mamytov", [("a", Role.TECHNICIAN)]),
    ("tech4@salymbekov.example.com", "Jyldyz Orozova", [("a", Role.TECHNICIAN)]),
    ("admin@salymbekov-hospital.example.com", "Kanat Beishenaliev", [("b", Role.ADMIN)]),
    ("requester1@salymbekov-hospital.example.com", "Leila Usenova", [("b", Role.REQUESTER)]),
    ("requester2@salymbekov-hospital.example.com", "Marat Zhakypov", [("b", Role.REQUESTER)]),
    ("tech1@salymbekov-hospital.example.com", "Nurlan Sydykov", [("b", Role.TECHNICIAN)]),
    ("tech2@salymbekov-hospital.example.com", "Olga Petrova", [("b", Role.TECHNICIAN)]),
    # One person, two organizations, two different roles (SEED-03 / ROLE-02).
    (
        "multi@salymbekov.example.com",
        "Timur Akmatov",
        [("a", Role.DISPATCHER), ("b", Role.REQUESTER)],
    ),
]

SKILLS = {
    "a": ["Electrical", "Plumbing", "HVAC", "Elevator", "General"],
    "b": ["Electrical", "Plumbing", "General"],
}

TECH_SKILLS = {
    "tech1@salymbekov.example.com": ["Electrical", "Elevator", "General"],
    "tech2@salymbekov.example.com": ["Plumbing", "General"],
    "tech3@salymbekov.example.com": ["HVAC", "Electrical"],
    "tech4@salymbekov.example.com": ["General", "Plumbing"],
    "tech1@salymbekov-hospital.example.com": ["Plumbing", "General"],
    "tech2@salymbekov-hospital.example.com": ["Electrical", "General"],
}
# Technicians who also work Saturdays (handy for weekend demos).
SATURDAY_TECHS = {"tech2@salymbekov.example.com", "tech1@salymbekov-hospital.example.com"}

# key, name, description, duration, required skills, enabled
CATEGORIES: dict[str, list[tuple[str, str, str, int, list[str], bool]]] = {
    "a": [
        (
            "electrical",
            "Electrical repair",
            "Wiring, sockets, lighting, panels.",
            90,
            ["Electrical"],
            True,
        ),
        ("plumbing", "Plumbing", "Leaks, drains, fixtures, water supply.", 60, ["Plumbing"], True),
        (
            "hvac",
            "HVAC service",
            "Heating, ventilation, and air conditioning.",
            120,
            ["HVAC"],
            True,
        ),
        (
            "elevator",
            "Elevator maintenance",
            "Lift inspection and repair.",
            120,
            ["Elevator", "Electrical"],
            True,
        ),
        (
            "general",
            "General maintenance",
            "Doors, locks, furniture, minor repairs.",
            60,
            ["General"],
            True,
        ),
        ("fire", "Fire safety (legacy)", "Replaced by an external contractor.", 60, [], False),
    ],
    "b": [
        ("plumbing", "Plumbing", "Leaks, drains, fixtures, water supply.", 60, ["Plumbing"], True),
        ("general", "General repairs", "Doors, locks, minor repairs.", 60, ["General"], True),
    ],
}

# key, name, address, contact instructions, shared
PROPERTIES: dict[str, list[tuple[str, str, str, str | None, bool]]] = {
    # Every facility of organization "a" is restricted (is_shared=False): a requester can
    # only file requests for the facilities of their own campus (see PROPERTY_CAMPUS and
    # CAMPUS_REQUESTERS below).
    "a": [
        # --- Salymbekov University main campus ---------------------------------
        (
            "su_main",
            "SU Main Academic Building",
            "Salymbekov University main campus, Bishkek",
            "Report to the security desk, floor 1.",
            False,
        ),
        (
            "su_medical",
            "SU Medical Faculty Building",
            "Salymbekov University main campus, Bishkek",
            "Call the facilities desk on arrival.",
            False,
        ),
        (
            "su_canteen",
            "SU Student Canteen and Commons",
            "Salymbekov University main campus, Bishkek",
            None,
            False,
        ),
        (
            "su_clinic",
            "SU University Teaching Clinic",
            "Salymbekov University main campus, Bishkek",
            "Quiet hours 13:00-15:00.",
            False,
        ),
        (
            "su_library",
            "SU Library and Learning Center",
            "Salymbekov University main campus, Bishkek",
            "Check in at the library service desk.",
            False,
        ),
        (
            "su_depot",
            "SU Campus Maintenance Depot",
            "Salymbekov University main campus, Bishkek",
            None,
            False,
        ),
        (
            "su_it",
            "SU IT Data Center",
            "Salymbekov University main campus, Bishkek",
            "Escort required. ID check at reception.",
            False,
        ),
        # --- AIT campus --------------------------------------------------------
        (
            "ait_main",
            "AIT Main Building",
            "AIT campus, Bishkek",
            "Report to the AIT front desk.",
            False,
        ),
        (
            "ait_labs",
            "AIT Computer Labs",
            "AIT campus, Bishkek",
            "Ask the lab coordinator for access outside class hours.",
            False,
        ),
        # --- College campus ----------------------------------------------------
        (
            "college_main",
            "College Main Building",
            "Salymbekov University College campus, Bishkek",
            "Report to the college administration office.",
            False,
        ),
        (
            "college_workshop",
            "College Training Workshop",
            "Salymbekov University College campus, Bishkek",
            "Check in with the workshop instructor.",
            False,
        ),
    ],
    "b": [
        (
            "resort",
            "University Hospital Main Block",
            "Salymbekov University Hospital, Bishkek",
            "Ask for the duty nurse manager.",
            True,
        ),
        ("hotel", "Outpatient Department", "Salymbekov University Hospital, Bishkek", None, True),
        (
            "villas",
            "Hospital Administration Building",
            "Salymbekov University Hospital, Bishkek",
            "Gate code is provided by phone.",
            True,
        ),
    ],
}

# Which campus each facility of organization "a" belongs to, and which requesters work
# on that campus. A requester can only see and file requests for their own campus.
PROPERTY_CAMPUS = {
    "su_main": "su",
    "su_medical": "su",
    "su_canteen": "su",
    "su_clinic": "su",
    "su_library": "su",
    "su_depot": "su",
    "su_it": "su",
    "ait_main": "ait",
    "ait_labs": "ait",
    "college_main": "college",
    "college_workshop": "college",
}
CAMPUS_REQUESTERS = {
    "su": ["requester1@salymbekov.example.com", "requester2@salymbekov.example.com"],
    "ait": ["requester3@salymbekov.example.com"],
    "college": ["requester4@salymbekov.example.com"],
}
# Extra restriction inside a campus: only these requesters may use the facility.
PROPERTY_ONLY = {"su_it": ["requester1@salymbekov.example.com"]}

# key, property, code, name, type, serial, status
ASSETS: dict[str, list[tuple[str, str, str, str, str, str | None, AssetStatus]]] = {
    "a": [
        (
            "ahu1",
            "su_main",
            "AHU-001",
            "Rooftop air handling unit 1",
            "HVAC",
            "TR-88213",
            AssetStatus.ACTIVE,
        ),
        (
            "lift1",
            "su_main",
            "ELV-001",
            "Passenger elevator A",
            "Elevator",
            "OT-55120",
            AssetStatus.ACTIVE,
        ),
        (
            "lift2",
            "su_main",
            "ELV-002",
            "Passenger elevator B",
            "Elevator",
            "OT-55121",
            AssetStatus.ACTIVE,
        ),
        (
            "panel1",
            "su_main",
            "ELP-001",
            "Main distribution panel",
            "Electrical",
            None,
            AssetStatus.ACTIVE,
        ),
        (
            "boiler1",
            "su_medical",
            "BLR-001",
            "Gas boiler",
            "Heating",
            "VS-10422",
            AssetStatus.ACTIVE,
        ),
        (
            "pump1",
            "su_medical",
            "PMP-001",
            "Booster pump",
            "Plumbing",
            "GF-7781",
            AssetStatus.OUT_OF_SERVICE,
        ),
        (
            "chiller1",
            "su_canteen",
            "CHL-001",
            "Water chiller",
            "HVAC",
            "CR-30019",
            AssetStatus.ACTIVE,
        ),
        (
            "gen1",
            "su_clinic",
            "GEN-001",
            "Backup generator",
            "Electrical",
            "CT-90455",
            AssetStatus.ACTIVE,
        ),
        (
            "ac1",
            "su_library",
            "SPL-001",
            "Split AC, reading hall",
            "HVAC",
            None,
            AssetStatus.ACTIVE,
        ),
        ("dock1", "su_depot", "DCK-001", "Loading dock door", "Doors", None, AssetStatus.ACTIVE),
        (
            "oldboiler",
            "su_medical",
            "BLR-000",
            "Old coal boiler",
            "Heating",
            "SU-1987",
            AssetStatus.RETIRED,
        ),
        (
            "ait_ac1",
            "ait_labs",
            "AIT-AC-001",
            "Computer lab precision AC",
            "HVAC",
            "AIT-40021",
            AssetStatus.ACTIVE,
        ),
        (
            "ait_ups1",
            "ait_labs",
            "AIT-UPS-001",
            "Computer lab UPS",
            "Electrical",
            None,
            AssetStatus.ACTIVE,
        ),
        (
            "college_boiler",
            "college_main",
            "COL-BLR-001",
            "College heating boiler",
            "Heating",
            "COL-55310",
            AssetStatus.ACTIVE,
        ),
        (
            "college_fan",
            "college_workshop",
            "COL-FAN-001",
            "Workshop extraction fan",
            "HVAC",
            None,
            AssetStatus.ACTIVE,
        ),
    ],
    "b": [
        (
            "pool1",
            "resort",
            "POL-001",
            "Hydrotherapy pool pump",
            "Plumbing",
            "HY-2210",
            AssetStatus.ACTIVE,
        ),
        (
            "heater1",
            "resort",
            "WHT-001",
            "Water heater, block A",
            "Plumbing",
            None,
            AssetStatus.ACTIVE,
        ),
        ("door1", "hotel", "DOR-001", "Lobby automatic door", "Doors", None, AssetStatus.ACTIVE),
        (
            "gate1",
            "villas",
            "GTE-001",
            "Main gate motor",
            "Electrical",
            "CM-4410",
            AssetStatus.ACTIVE,
        ),
    ],
}

# code, name, unit, stock, reorder threshold, unit price (tyiyn)
INVENTORY: dict[str, list[tuple[str, str, str, int, int, int]]] = {
    "a": [
        ("FLT-G4", "Air filter G4 592x592", "pcs", 40, 10, 85000),
        ("BLT-A42", "V-belt A42", "pcs", 12, 4, 42000),
        ("CBL-2.5", "Copper cable 3x2.5", "m", 300, 50, 9500),
        ("BRK-16A", "Circuit breaker 16A", "pcs", 25, 8, 31000),
        ("LED-18W", "LED tube 18W", "pcs", 60, 20, 18000),
        ("PPR-20", "PPR pipe 20mm", "m", 120, 30, 6500),
        ("VLV-15", "Ball valve 1/2 inch", "pcs", 18, 6, 27000),
        ("SLN-01", "Silicone sealant", "pcs", 2, 5, 22000),  # low stock (SEED-03)
        ("GSK-SET", "Gasket set", "set", 9, 3, 15000),
        ("RFG-410", "Refrigerant R410A", "kg", 15, 5, 120000),
        ("LCK-CYL", "Lock cylinder", "pcs", 7, 3, 65000),
        ("HNG-DR", "Door hinge", "pcs", 30, 10, 12000),
        ("OIL-ELV", "Elevator guide oil", "l", 5, 5, 54000),  # at threshold
        ("FUS-10A", "Fuse 10A", "pcs", 0, 10, 4000),  # out of stock
    ],
    "b": [
        ("PPR-20", "PPR pipe 20mm", "m", 80, 20, 6800),
        ("VLV-15", "Ball valve 1/2 inch", "pcs", 10, 4, 28000),
        ("SLN-01", "Silicone sealant", "pcs", 14, 5, 23000),
        ("PMP-SEAL", "Pump mechanical seal", "pcs", 3, 3, 185000),
        ("HNG-DR", "Door hinge", "pcs", 16, 6, 12500),
        ("LED-18W", "LED tube 18W", "pcs", 24, 10, 18500),
    ],
}

# (title, category, asset, property, priority)
ISSUES_A: list[tuple[str, str, str | None, str, str]] = [
    ("Air handling unit making a grinding noise", "hvac", "ahu1", "su_main", "HIGH"),
    ("Elevator A stops between floors", "elevator", "lift1", "su_main", "HIGH"),
    ("Water leak under the kitchen sink", "plumbing", None, "su_medical", "NORMAL"),
    ("Flickering lights in the east corridor", "electrical", None, "su_main", "NORMAL"),
    ("Boiler pressure keeps dropping", "plumbing", "boiler1", "su_medical", "HIGH"),
    ("Office door lock is jammed", "general", None, "su_clinic", "LOW"),
    ("Chiller shows a high-pressure alarm", "hvac", "chiller1", "su_canteen", "HIGH"),
    ("Power sockets dead in meeting room 3", "electrical", "panel1", "su_main", "NORMAL"),
    ("Blocked drain in the restroom", "plumbing", None, "su_canteen", "NORMAL"),
    ("Reading hall air conditioner not cooling", "hvac", "ac1", "su_library", "NORMAL"),
    ("Loading dock door will not close fully", "general", "dock1", "su_depot", "NORMAL"),
    ("Generator fails the weekly self-test", "electrical", "gen1", "su_clinic", "HIGH"),
    ("Ceiling tile damaged by moisture", "general", None, "su_library", "LOW"),
    ("Elevator B door closes too slowly", "elevator", "lift2", "su_main", "NORMAL"),
    ("Tap dripping in the reception area", "plumbing", None, "su_clinic", "LOW"),
    ("Emergency exit sign is not lit", "electrical", None, "su_canteen", "NORMAL"),
    ("Booster pump vibrates heavily", "plumbing", "pump1", "su_medical", "NORMAL"),
    ("Broken window handle on floor 4", "general", None, "su_main", "LOW"),
    ("Thermostat reads the wrong temperature", "hvac", None, "su_medical", "LOW"),
    ("Circuit breaker trips every morning", "electrical", "panel1", "su_main", "HIGH"),
    ("Toilet cistern runs continuously", "plumbing", None, "su_library", "NORMAL"),
    # AIT campus
    ("Computer lab air conditioner is not cooling", "hvac", "ait_ac1", "ait_labs", "HIGH"),
    ("UPS in the computer lab beeps constantly", "electrical", "ait_ups1", "ait_labs", "NORMAL"),
    ("Projector mount is loose in room 204", "general", None, "ait_main", "LOW"),
    ("Water leak in the AIT second-floor restroom", "plumbing", None, "ait_main", "NORMAL"),
    # College campus
    (
        "College boiler pressure keeps dropping",
        "plumbing",
        "college_boiler",
        "college_main",
        "HIGH",
    ),
    ("Workshop extraction fan is very loud", "hvac", "college_fan", "college_workshop", "NORMAL"),
]

ISSUES_B: list[tuple[str, str, str | None, str, str]] = [
    ("Hydrotherapy pool pump loses prime overnight", "plumbing", "pool1", "resort", "HIGH"),
    ("Lobby door sensor is unreliable", "general", "door1", "hotel", "NORMAL"),
    ("No hot water in block A", "plumbing", "heater1", "resort", "HIGH"),
    ("Office 7 door sticks", "general", None, "villas", "LOW"),
    ("Shower drain is slow in room 214", "plumbing", None, "hotel", "NORMAL"),
]

# Target status for each seeded request, in creation order (oldest first).
PLAN_A = (
    ["CLOSED"] * 4
    + ["COMPLETED"] * 3
    + ["REOPENED"] * 2
    + ["CANCELED"] * 2
    + ["COMPLETED"] * 2
    + ["BLOCKED"] * 2
    + ["IN_PROGRESS"] * 4
    + ["ACCEPTED"] * 4
    + ["SCHEDULED"] * 5
    + ["TRIAGED"] * 6
    + ["SUBMITTED"] * 8
)
PLAN_B = ["CLOSED", "COMPLETED", "CANCELED", "SCHEDULED", "SCHEDULED", "TRIAGED", "TRIAGED"] + [
    "SUBMITTED"
] * 3


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


@dataclass
class Timeline:
    anchor: datetime  # the real "now" when the seed runs

    def workday(self, offset: int) -> date:
        """offset 0 = latest business day <= today; negative = earlier; positive = later."""
        day = self.anchor.astimezone(TZ).date()
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        step = 1 if offset > 0 else -1
        remaining = abs(offset)
        while remaining:
            day += timedelta(days=step)
            if day.weekday() < 5:
                remaining -= 1
        return day

    def at(self, offset: int, hour: int, minute: int = 0) -> datetime:
        return datetime.combine(self.workday(offset), time(hour, minute), TZ).astimezone(UTC)

    def past(self, instant: datetime) -> datetime:
        """Never let a simulated action happen after the real present."""
        return min(instant, self.anchor - timedelta(minutes=2))


def demo_image(label: str, color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (640, 420), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 620, 400), outline=(255, 255, 255), width=4)
    draw.text((40, 40), "FixFlow demo evidence", fill=(255, 255, 255))
    draw.text((40, 70), label[:70], fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


async def seed_reference(db: AsyncSession, timeline: Timeline) -> None:
    created = timeline.at(-30, 9)
    clock.pin(created)
    password_hash = hash_password(DEMO_PASSWORD)

    for key, (name, slug) in ORGS.items():
        db.add(Organization(id=sid(f"org:{key}"), name=name, slug=slug, timezone="Asia/Bishkek"))
        for weekday in range(5):  # SLA-01 default: Monday-Friday 09:00-18:00
            db.add(
                BusinessHours(
                    id=sid(f"hours:{key}:{weekday}"),
                    org_id=sid(f"org:{key}"),
                    weekday=weekday,
                    opens_at=time(9),
                    closes_at=time(18),
                )
            )
    await db.flush()

    for key, names in SKILLS.items():
        for name in names:
            db.add(Skill(id=sid(f"skill:{key}:{name}"), org_id=sid(f"org:{key}"), name=name))

    for email, full_name, _ in USERS:
        db.add(
            User(
                id=sid(f"user:{email}"),
                email=email,
                full_name=full_name,
                password_hash=password_hash,
            )
        )
    await db.flush()

    for email, _, memberships in USERS:
        for org, role in memberships:
            membership_id = sid(f"membership:{org}:{email}")
            db.add(
                OrganizationMembership(
                    id=membership_id,
                    org_id=sid(f"org:{org}"),
                    user_id=sid(f"user:{email}"),
                    role=role,
                )
            )
            await db.flush()
            if role != Role.TECHNICIAN:
                continue
            tech_id = sid(f"tech:{org}:{email}")
            db.add(
                TechnicianProfile(
                    id=tech_id,
                    org_id=sid(f"org:{org}"),
                    membership_id=membership_id,
                    user_id=sid(f"user:{email}"),
                    title="Field technician",
                    phone="+996 555 010 0" + str(len(email) % 90 + 10),
                )
            )
            await db.flush()
            for skill in TECH_SKILLS[email]:
                db.add(
                    TechnicianSkill(
                        org_id=sid(f"org:{org}"),
                        technician_id=tech_id,
                        skill_id=sid(f"skill:{org}:{skill}"),
                    )
                )
            days = range(6) if email in SATURDAY_TECHS else range(5)
            for weekday in days:
                db.add(
                    TechnicianAvailability(
                        id=sid(f"avail:{email}:{weekday}"),
                        org_id=sid(f"org:{org}"),
                        technician_id=tech_id,
                        weekday=weekday,
                        starts_at=time(9),
                        ends_at=time(18),
                    )
                )

    # Dated time off: tech4 is away for two business days next week (SCHED-01).
    db.add(
        TechnicianTimeOff(
            id=sid("timeoff:tech4"),
            org_id=sid("org:a"),
            technician_id=sid("tech:a:tech4@salymbekov.example.com"),
            start_at=timeline.at(6, 0),
            end_at=timeline.at(8, 0),
            reason="Annual leave",
        )
    )

    for org, categories in CATEGORIES.items():
        for key, name, description, duration, skills, enabled in categories:
            category_id = sid(f"category:{org}:{key}")
            db.add(
                ServiceCategory(
                    id=category_id,
                    org_id=sid(f"org:{org}"),
                    name=name,
                    description=description,
                    default_duration_minutes=duration,
                    is_enabled=enabled,
                )
            )
            await db.flush()
            for skill in skills:
                db.add(
                    CategorySkill(
                        org_id=sid(f"org:{org}"),
                        category_id=category_id,
                        skill_id=sid(f"skill:{org}:{skill}"),
                    )
                )

    for org, properties in PROPERTIES.items():
        for key, name, address, instructions, shared in properties:
            db.add(
                Property(
                    id=sid(f"property:{org}:{key}"),
                    org_id=sid(f"org:{org}"),
                    name=name,
                    address=address,
                    contact_instructions=instructions,
                    is_shared=shared,
                )
            )
    await db.flush()
    # Campus scoping (ASSET-03): every facility of organization "a" is restricted, and each
    # requester is granted only the facilities of their own campus. An AIT requester can
    # therefore never file a request for a Salymbekov University facility, and vice versa.
    for prop_key, campus in PROPERTY_CAMPUS.items():
        for email in PROPERTY_ONLY.get(prop_key, CAMPUS_REQUESTERS[campus]):
            db.add(
                PropertyRequester(
                    org_id=sid("org:a"),
                    property_id=sid(f"property:a:{prop_key}"),
                    membership_id=sid(f"membership:a:{email}"),
                )
            )

    for org, assets in ASSETS.items():
        for key, prop, code, name, asset_type, serial, status in assets:
            db.add(
                Asset(
                    id=sid(f"asset:{org}:{key}"),
                    org_id=sid(f"org:{org}"),
                    property_id=sid(f"property:{org}:{prop}"),
                    code=code,
                    name=name,
                    asset_type=asset_type,
                    serial_number=serial,
                    installed_on=date(2021, 3, 15),
                    status=status,
                )
            )

    for org, items in INVENTORY.items():
        for code, name, unit, stock, threshold, price in items:
            db.add(
                InventoryItem(
                    id=sid(f"item:{org}:{code}"),
                    org_id=sid(f"org:{org}"),
                    code=code,
                    name=name,
                    unit=unit,
                    stock_quantity=stock,
                    reorder_threshold=threshold,
                    unit_price_minor=price,
                )
            )
    await db.commit()


# ---------------------------------------------------------------------------
# API replay
# ---------------------------------------------------------------------------


class SeedError(RuntimeError):
    pass


@dataclass
class Actor:
    client: httpx.AsyncClient
    email: str
    org: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Organization-ID": str(sid(f"org:{self.org}")),
        }

    async def call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.client.request(
            method, f"/api/v1{path}", headers=self.headers, **kwargs
        )
        if response.status_code >= 400:
            raise SeedError(
                f"{self.email} {method} {path} -> {response.status_code} {response.text}"
            )
        return response.json()

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return await self.call("POST", path, json=body or {})

    async def upload(
        self,
        request_id: str,
        kind: str,
        label: str,
        color: tuple[int, int, int],
        command: str,
        note_id: str | None = None,
    ) -> Any:
        data = {"kind": kind, "client_command_id": command}
        if note_id:
            data["note_id"] = note_id
        return await self.call(
            "POST",
            f"/requests/{request_id}/files",
            data=data,
            files={"file": (f"{kind.lower()}.png", demo_image(label, color), "image/png")},
        )


@dataclass
class OrgWorld:
    key: str
    dispatcher: Actor
    requesters: list[Actor]
    technicians: dict[str, Actor]
    booked: set[tuple[str, date, int]] = field(default_factory=set)
    rotation: Any = None

    def requester_for(self, prop: str, index: int) -> Actor:
        """A requester who is allowed to file for this facility (campus scoping)."""
        if self.key == "a":
            allowed = PROPERTY_ONLY.get(prop, CAMPUS_REQUESTERS[PROPERTY_CAMPUS[prop]])
            pool = [r for r in self.requesters if r.email in allowed]
        else:
            pool = self.requesters
        return pool[index % len(pool)]

    def category_skills(self, category: str) -> set[str]:
        return next(set(c[4]) for c in CATEGORIES[self.key] if c[0] == category)

    def pick_slot(
        self, timeline: Timeline, category: str, first_offset: int
    ) -> tuple[str, datetime, datetime]:
        """First free two-hour slot of an eligible technician on/after a business day."""
        needed = self.category_skills(category)
        eligible = [email for email in self.technicians if needed <= set(TECH_SKILLS[email])]
        for offset in range(first_offset, first_offset + 15):
            day = timeline.workday(offset)
            for hour in SLOT_HOURS:
                for email in eligible:
                    # Keep tech4's leave days free.
                    if email.startswith("tech4@") and offset in (6, 7):
                        continue
                    if (email, day, hour) not in self.booked:
                        self.booked.add((email, day, hour))
                        start = datetime.combine(day, time(hour), TZ).astimezone(UTC)
                        return email, start, start + timedelta(hours=2)
        raise SeedError(f"no free slot for {category}")


async def replay_request(
    world: OrgWorld,
    timeline: Timeline,
    index: int,
    issue: tuple[str, str, str | None, str, str],
    target: str,
    created_offset: int,
) -> dict[str, Any]:
    title, category, asset, prop, priority = issue
    org = world.key
    requester = world.requester_for(prop, index)
    dispatcher = world.dispatcher
    cmd = f"seed-{org}-{index:03d}"

    created_at = timeline.past(timeline.at(created_offset, 9 + index % 7, (index * 13) % 60))
    if created_offset == 0:
        created_at = timeline.anchor - timedelta(minutes=12 * (index % 9 + 1))
    clock.pin(created_at)
    req = await requester.post(
        "/requests",
        {
            "title": title,
            "description": (
                f"{title}. Reported by on-site staff during a routine walk-through; "
                "please inspect and repair. Access details are on the property record."
            ),
            "category_id": str(sid(f"category:{org}:{category}")),
            "property_id": str(sid(f"property:{org}:{prop}")),
            "asset_id": str(sid(f"asset:{org}:{asset}")) if asset else None,
            "priority": priority,
        },
    )
    rid = req["id"]
    if index % 5 == 0:
        await requester.upload(
            rid, "INTAKE", f"{req['reference']} intake photo", (70, 90, 150), f"{cmd}-intake"
        )
    if index % 6 == 1:
        await requester.post(
            f"/requests/{rid}/notes",
            {
                "body": "Happy to give access any weekday morning.",
                "client_command_id": f"{cmd}-rnote",
            },
        )
    if target == "SUBMITTED":
        return req
    if target == "CANCELED" and index % 2 == 0:
        clock.pin(timeline.past(created_at + timedelta(minutes=20)))
        return await requester.post(f"/requests/{rid}/cancel", {"reason": "Resolved it ourselves."})

    clock.pin(timeline.past(created_at + timedelta(minutes=35)))
    await dispatcher.post(
        f"/requests/{rid}/triage", {"triage_notes": "Checked details with the requester."}
    )
    if index % 4 == 2:
        await dispatcher.post(
            f"/requests/{rid}/notes",
            {
                "body": "Parts are likely in stock; no supplier order needed.",
                "visibility": "INTERNAL",
                "client_command_id": f"{cmd}-dnote",
            },
        )
    if target == "CANCELED":
        clock.pin(timeline.past(created_at + timedelta(hours=1)))
        return await dispatcher.post(
            f"/requests/{rid}/cancel", {"reason": "Duplicate report from another department."}
        )
    if target == "TRIAGED":
        return req

    historical = target in ("IN_PROGRESS", "BLOCKED", "COMPLETED", "REOPENED", "CLOSED")
    clock.pin(timeline.past(created_at + timedelta(hours=1)))
    tech_email, start_at, end_at = world.pick_slot(
        timeline, category, created_offset + 1 if historical else 1
    )
    await dispatcher.post(
        f"/requests/{rid}/assign",
        {
            "technician_id": str(sid(f"tech:{org}:{tech_email}")),
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
        },
    )
    if target == "SCHEDULED":
        return req
    technician = world.technicians[tech_email]
    clock.pin(timeline.past(created_at + timedelta(hours=2)))
    await technician.post(f"/requests/{rid}/accept")
    if target == "ACCEPTED":
        return req

    clock.pin(timeline.past(start_at + timedelta(minutes=5)))
    await technician.post(f"/requests/{rid}/start")
    await technician.post(
        f"/requests/{rid}/notes",
        {"body": "On site. Starting diagnostics.", "client_command_id": f"{cmd}-tnote"},
    )
    if index % 3 == 0:
        items = INVENTORY[org]
        code = items[index % 5][0]
        await technician.post(
            f"/requests/{rid}/materials",
            {
                "item_id": str(sid(f"item:{org}:{code}")),
                "quantity": 1 + index % 2,
                "client_command_id": f"{cmd}-mat",
            },
        )
    if target == "IN_PROGRESS":
        return req
    if target == "BLOCKED":
        clock.pin(timeline.past(start_at + timedelta(minutes=50)))
        return await technician.post(
            f"/requests/{rid}/block",
            {"reason": "Waiting for a replacement part from the supplier."},
        )

    clock.pin(timeline.past(start_at + timedelta(minutes=95)))
    await technician.upload(
        rid, "COMPLETION", f"{req['reference']} work completed", (40, 120, 80), f"{cmd}-done"
    )
    await technician.post(
        f"/requests/{rid}/complete",
        {
            "completion_note": "Fault located and repaired. Tested for 15 minutes under normal load; operating correctly."
        },
    )
    if target == "COMPLETED":
        return req
    clock.pin(timeline.past(end_at + timedelta(hours=3)))
    if target == "REOPENED":
        return await requester.post(
            f"/requests/{rid}/reopen", {"reason": "The problem came back the next morning."}
        )
    await requester.post(f"/requests/{rid}/close")
    await requester.post(
        f"/requests/{rid}/feedback",
        {"rating": 5 - index % 2, "comment": "Quick and tidy work, thank you."},
    )
    return req


async def seed_estimates(
    world: OrgWorld, timeline: Timeline, by_status: dict[str, list[dict[str, Any]]]
) -> None:
    """One request in each estimate state (SEED-02, EST-02)."""
    dispatcher = world.dispatcher

    def body(labor_minutes: int, lines: list[tuple[str, int, int]]) -> dict[str, Any]:
        return {
            "labor_minutes": labor_minutes,
            "labor_rate_minor": 120000,
            "notes": "Includes travel within Bishkek.",
            "lines": [
                {"description": d, "quantity": q, "unit_price_minor": p} for d, q, p in lines
            ],
        }

    def requester_for(req: dict[str, Any]) -> Actor:
        return next(a for a in world.requesters if req["requester_name"] == NAMES[a.email])

    clock.pin(timeline.anchor - timedelta(hours=5))
    # DRAFT
    triaged = by_status["TRIAGED"]
    await dispatcher.post(
        f"/requests/{triaged[0]['id']}/estimates", body(60, [("Ball valve 1/2 inch", 2, 27000)])
    )
    # REJECTED
    rejected = await dispatcher.post(
        f"/requests/{triaged[1]['id']}/estimates", body(180, [("Compressor contactor", 1, 480000)])
    )
    await dispatcher.post(f"/estimates/{rejected['id']}/submit")
    clock.pin(timeline.anchor - timedelta(hours=4))
    await requester_for(triaged[1]).post(
        f"/estimates/{rejected['id']}/reject",
        {"version": 1, "reason": "Too expensive; please quote a repair instead of replacement."},
    )
    # APPROVED
    scheduled = by_status["SCHEDULED"]
    approved = await dispatcher.post(
        f"/requests/{scheduled[0]['id']}/estimates", body(90, [("LED tube 18W", 6, 18000)])
    )
    await dispatcher.post(f"/estimates/{approved['id']}/submit")
    await requester_for(scheduled[0]).post(f"/estimates/{approved['id']}/approve", {"version": 1})
    # SUPERSEDED v1 (rejected) -> APPROVED v2
    v1 = await dispatcher.post(
        f"/requests/{scheduled[1]['id']}/estimates",
        body(240, [("Gasket set", 2, 15000), ("Refrigerant R410A", 3, 120000)]),
    )
    await dispatcher.post(f"/estimates/{v1['id']}/submit")
    await requester_for(scheduled[1]).post(
        f"/estimates/{v1['id']}/reject", {"version": 1, "reason": "Labor time looks too high."}
    )
    clock.pin(timeline.anchor - timedelta(hours=3))
    v2 = await dispatcher.post(
        f"/requests/{scheduled[1]['id']}/estimates",
        body(150, [("Gasket set", 2, 15000), ("Refrigerant R410A", 3, 120000)]),
    )
    await dispatcher.post(f"/estimates/{v2['id']}/submit")
    await requester_for(scheduled[1]).post(f"/estimates/{v2['id']}/approve", {"version": 2})
    # AWAITING_APPROVAL on an accepted job: the technician cannot start yet (EST-04).
    accepted = by_status["ACCEPTED"]
    waiting = await dispatcher.post(
        f"/requests/{accepted[0]['id']}/estimates", body(120, [("Circuit breaker 16A", 3, 31000)])
    )
    await dispatcher.post(f"/estimates/{waiting['id']}/submit")


NAMES = {email: name for email, name, _ in USERS}


async def seed_maintenance(world: OrgWorld, timeline: Timeline) -> None:
    dispatcher = world.dispatcher
    org = world.key
    today = timeline.anchor.astimezone(TZ).date()
    clock.pin(timeline.at(-16, 10))
    plans = (
        [
            (
                "ahu1",
                "hvac",
                "Weekly AHU filter and belt check",
                "WEEKLY",
                today - timedelta(days=14),
                "NORMAL",
            ),
            (
                "lift1",
                "elevator",
                "Monthly elevator safety inspection",
                "MONTHLY",
                today + timedelta(days=9),
                "HIGH",
            ),
            (
                "gen1",
                "electrical",
                "Monthly generator load test",
                "MONTHLY",
                today - timedelta(days=40),
                "NORMAL",
            ),
        ]
        if org == "a"
        else [
            (
                "pool1",
                "plumbing",
                "Weekly hydrotherapy pool pump inspection",
                "WEEKLY",
                today - timedelta(days=3),
                "NORMAL",
            )
        ]
    )
    created = []
    for asset, category, title, recurrence, first_date, priority in plans:
        created.append(
            await dispatcher.post(
                "/maintenance-plans",
                {
                    "asset_id": str(sid(f"asset:{org}:{asset}")),
                    "category_id": str(sid(f"category:{org}:{category}")),
                    "title": title,
                    "description": f"{title}. Follow the manufacturer checklist and record readings in the completion note.",
                    "priority": priority,
                    "first_date": first_date.isoformat(),
                    "recurrence": recurrence,
                },
            )
        )
    if org == "a":
        # Generate history up to a week ago; the newest occurrence stays due (SEED-03).
        clock.pin(timeline.past(timeline.at(-1, 9)))
        await dispatcher.post(
            "/maintenance-plans/generate", {"as_of": (today - timedelta(days=7)).isoformat()}
        )
        # A disabled plan shows that disabling stops future generation (PM-04).
        await dispatcher.call(
            "PATCH", f"/maintenance-plans/{created[2]['id']}", json={"is_enabled": False}
        )


async def seed_collision_candidate(world: OrgWorld, timeline: Timeline) -> None:
    """A triaged request whose preferred visit equals an already-booked slot (SEED-02)."""
    clock.pin(timeline.anchor - timedelta(hours=2))
    requester = world.requesters[0]
    dispatcher = world.dispatcher
    tech = "tech1@salymbekov.example.com"
    start = timeline.at(3, 14)
    end = start + timedelta(hours=2)
    base = {
        "category_id": str(sid("category:a:electrical")),
        "property_id": str(sid("property:a:su_main")),
        "priority": "NORMAL",
    }
    booked = await requester.post(
        "/requests",
        {
            **base,
            "title": "Replace lobby light fittings",
            "description": "Six fittings in the main lobby flicker and need replacement before the university event.",
        },
    )
    await dispatcher.post(f"/requests/{booked['id']}/triage")
    await dispatcher.post(
        f"/requests/{booked['id']}/assign",
        {
            "technician_id": str(sid(f"tech:a:{tech}")),
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
    )
    candidate = await requester.post(
        "/requests",
        {
            **base,
            "title": "Collision candidate: panel inspection",
            "description": "Demo request. Assigning Farid Abdyldaev to the preferred slot conflicts with the lobby light job.",
            "preferred_start_at": start.isoformat(),
            "preferred_end_at": end.isoformat(),
        },
    )
    await dispatcher.post(
        f"/requests/{candidate['id']}/triage",
        {"triage_notes": "Try the preferred slot with Farid to see a 409 schedule conflict."},
    )


async def already_seeded(db: AsyncSession) -> bool:
    return bool(await db.scalar(select(Organization.id).where(Organization.id == sid("org:a"))))


async def run() -> None:
    from app.main import app  # imported late so the CLI can set env first

    timeline = Timeline(anchor=datetime.now(UTC).replace(microsecond=0))
    async with SessionLocal() as db:
        if await already_seeded(db):
            print("[seed] demo data already present; nothing to do")
            return
        print("[seed] creating reference data ...")
        await seed_reference(db, timeline)
        tokens: dict[str, str] = {}
        for email, _, _ in USERS:
            tokens[email] = f"seed-{uuid.uuid4().hex}"
            db.add(
                AuthSession(
                    user_id=sid(f"user:{email}"),
                    token_hash=hash_token(tokens[email]),
                    expires_at=datetime.now(UTC) + timedelta(hours=2),
                )
            )
        await db.commit()

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://seed") as client:

            def actor(email: str, org: str) -> Actor:
                return Actor(client=client, email=email, org=org, token=tokens[email])

            world_a = OrgWorld(
                key="a",
                dispatcher=actor("dispatcher@salymbekov.example.com", "a"),
                requesters=[
                    actor(f"requester{i}@salymbekov.example.com", "a") for i in (1, 2, 3, 4)
                ],
                technicians={
                    e: actor(e, "a") for e in TECH_SKILLS if e.endswith("@salymbekov.example.com")
                },
            )
            world_b = OrgWorld(
                key="b",
                dispatcher=actor("admin@salymbekov-hospital.example.com", "b"),
                requesters=[
                    actor("requester1@salymbekov-hospital.example.com", "b"),
                    actor("requester2@salymbekov-hospital.example.com", "b"),
                    actor("multi@salymbekov.example.com", "b"),
                ],
                technicians={
                    e: actor(e, "b")
                    for e in TECH_SKILLS
                    if e.endswith("@salymbekov-hospital.example.com")
                },
            )
            # Reserved for the collision-candidate demo below.
            world_a.booked.add(("tech1@salymbekov.example.com", timeline.workday(3), 14))
            for world, issues, plan in ((world_a, ISSUES_A, PLAN_A), (world_b, ISSUES_B, PLAN_B)):
                print(f"[seed] replaying {len(plan)} requests for organization {world.key} ...")
                by_status: dict[str, list[dict[str, Any]]] = {}
                total = len(plan)
                for index, target in enumerate(plan):
                    # Oldest requests first: offsets run from about -17 business days to today.
                    remaining = total - 1 - index
                    recent = {
                        "SUBMITTED": 0,
                        "TRIAGED": 1,
                        "SCHEDULED": 1,
                        "ACCEPTED": 2,
                        "IN_PROGRESS": 2,
                        "BLOCKED": 3,
                    }
                    offset = -recent[target] if target in recent else -(2 + remaining // 5)
                    if target == "SUBMITTED" and index % 3 == 0:
                        offset = -1
                    title, category, asset, prop, priority = issues[index % len(issues)]
                    if index >= len(issues):
                        title = f"{title} (report {index // len(issues) + 1})"
                    req = await replay_request(
                        world,
                        timeline,
                        index,
                        (title, category, asset, prop, priority),
                        target,
                        offset,
                    )
                    by_status.setdefault(target, []).append(req)
                if world.key == "a":
                    await seed_estimates(world, timeline, by_status)
                    await seed_collision_candidate(world, timeline)
                    # One clearly overdue HIGH request that nobody has scheduled (SEED-02).
                    clock.pin(timeline.at(-5, 15, 30))
                    overdue = await world.requesters[1].post(
                        "/requests",
                        {
                            "title": "Server room cooling failure",
                            "description": "Temperature in the server room is rising. This demo request is deliberately left unscheduled so it is overdue.",
                            "category_id": str(sid("category:a:hvac")),
                            "property_id": str(sid("property:a:su_main")),
                            "priority": "HIGH",
                        },
                    )
                    clock.pin(timeline.at(-5, 16))
                    await world.dispatcher.post(
                        f"/requests/{overdue['id']}/triage",
                        {"triage_notes": "Waiting for HVAC capacity."},
                    )
                await seed_maintenance(world, timeline)
    finally:
        clock.release()
        async with SessionLocal() as db:
            await db.execute(
                delete(AuthSession).where(
                    AuthSession.token_hash.in_([hash_token(t) for t in tokens.values()])
                )
            )
            escalated = await escalate_overdue(db, datetime.now(UTC))
            await db.commit()
    print(f"[seed] done. {escalated} overdue request(s) escalated.")
    print(f"[seed] demo password for every account: {DEMO_PASSWORD}  (disposable, demo-only)")
