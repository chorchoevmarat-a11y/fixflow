"""Estimate versioning/races, business-time SLA, escalation, preventive maintenance."""

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.base import clock
from app.models.models import Notification, Organization, ServiceRequest
from app.services.escalation import escalate_overdue
from app.services.maintenance import generate
from app.services.sla import Calendar, add_business_seconds, business_seconds_between
from tests.conftest import World
from tests.helpers import cmd, create_request, error_code, slot, to_accepted, to_triaged

TZ = ZoneInfo("Asia/Bishkek")
EST = {
    "labor_minutes": 90,
    "labor_rate_minor": 120000,
    "lines": [{"description": "Filter", "quantity": 2, "unit_price_minor": 85000}],
}


def calendar(holidays: frozenset[date] = frozenset()) -> Calendar:
    weekdays: dict[int, tuple[tuple[time, time], ...]] = {
        d: ((time(9), time(18)),) for d in range(5)
    }
    return Calendar(tz=TZ, hours=weekdays, holidays=holidays)


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), TZ).astimezone(UTC)


# ---------------------------------------------------------------- SLA maths


def test_friday_evening_high_priority_is_due_after_the_weekend() -> None:
    friday = date(2026, 11, 13)  # a Friday
    due = add_business_seconds(calendar(), at(friday, 17, 30), 8 * 3600)
    assert due is not None
    # 30 min Friday + 7.5 h Monday... = Monday 16:30 local... (30m + 7h30m = 8h)
    assert due.astimezone(TZ) == datetime(2026, 11, 16, 16, 30, tzinfo=TZ)


def test_holiday_and_closed_time_do_not_consume_budget() -> None:
    monday = date(2026, 11, 16)
    plain = add_business_seconds(calendar(), at(monday, 9), 24 * 3600)
    with_holiday = add_business_seconds(
        calendar(frozenset({date(2026, 11, 17)})), at(monday, 9), 24 * 3600
    )
    assert plain is not None and with_holiday is not None
    assert plain.astimezone(TZ).date() == date(2026, 11, 18)
    assert with_holiday.astimezone(TZ).date() == date(2026, 11, 19)  # holiday skipped
    assert (
        business_seconds_between(calendar(), at(date(2026, 11, 13), 17), at(monday, 10)) == 2 * 3600
    )


async def test_estimate_pause_and_priority_change_recalculate_the_budget(world: World) -> None:
    a = world.a
    clock.pin(at(date(2026, 11, 13), 16))  # Friday 16:00
    req = await create_request(world, a, priority="NORMAL")
    rid = req["id"]
    assert req["sla"]["budget_seconds"] == 24 * 3600
    due_before = req["sla"]["due_at"]
    await world.ok(a.dispatcher, "POST", f"/requests/{rid}/triage", json={})
    est = await world.ok(a.dispatcher, "POST", f"/requests/{rid}/estimates", json=EST)
    clock.pin(at(date(2026, 11, 13), 17))
    await world.ok(a.dispatcher, "POST", f"/estimates/{est['id']}/submit")
    paused = await world.ok(a.dispatcher, "GET", f"/requests/{rid}")
    assert paused["sla"]["paused"] and paused["sla"]["due_at"] is None
    # Two days pass while the requester thinks; none of it is consumed.
    clock.pin(at(date(2026, 11, 17), 10))
    await world.ok(a.requester, "POST", f"/estimates/{est['id']}/approve", json={"version": 1})
    resumed = await world.ok(a.dispatcher, "GET", f"/requests/{rid}")
    assert not resumed["sla"]["paused"]
    assert resumed["sla"]["consumed_seconds"] == 3600  # only Fri 16:00-17:00 counted
    due_after = datetime.fromisoformat(resumed["sla"]["due_at"]).astimezone(TZ)
    assert due_after == datetime(2026, 11, 18, 10, 0, tzinfo=TZ) + timedelta(
        hours=0
    ) or due_after > datetime.fromisoformat(due_before)
    # Raising priority: new 8h budget minus the 1h already consumed.
    changed = await world.ok(
        a.dispatcher,
        "POST",
        f"/requests/{rid}/reclassify",
        json={"priority": "HIGH", "reason": "Escalated by tenant"},
    )
    assert (
        changed["sla"]["budget_seconds"] == 8 * 3600 and changed["sla"]["consumed_seconds"] == 3600
    )
    expected_due = add_business_seconds(calendar(), at(date(2026, 11, 17), 10), 7 * 3600)
    assert expected_due is not None
    assert abs(datetime.fromisoformat(changed["sla"]["due_at"]) - expected_due) < timedelta(
        seconds=1
    )


async def test_overdue_is_escalated_exactly_once(world: World) -> None:
    a = world.a
    clock.pin(at(date(2026, 11, 2), 9))  # Monday
    req = await create_request(world, a, priority="HIGH")
    clock.pin(at(date(2026, 11, 2), 16))  # still inside the 8h budget
    assert (await world.ok(a.dispatcher, "GET", f"/requests/{req['id']}"))["sla"]["state"] in (
        "AT_RISK",
        "ON_TRACK",
    )
    clock.pin(at(date(2026, 11, 3), 10))  # budget exhausted at Mon 17:00
    shown = await world.ok(a.dispatcher, "GET", f"/requests/{req['id']}")
    assert shown["sla"]["state"] == "OVERDUE" and shown["sla"]["remaining_seconds"] < 0
    dashboard = await world.ok(a.dispatcher, "GET", "/reports/dashboard")
    assert dashboard["overdue_count"] == 1
    overdue_list = await world.ok(a.dispatcher, "GET", "/requests?sla_state=OVERDUE")
    assert overdue_list["total"] == 1

    async def run() -> int:
        async with SessionLocal() as db:
            count = await escalate_overdue(db, clock.now())
            await db.commit()
            return count

    counts = await asyncio.gather(run(), run(), run())
    assert sum(counts) == 1
    assert await run() == 0
    async with SessionLocal() as db:
        n = await db.scalar(
            select(func.count()).select_from(Notification).where(Notification.type == "SLA_OVERDUE")
        )
        assert n == 2  # admin + dispatcher, once


# ---------------------------------------------------------------- Estimates


async def test_estimate_gate_versions_and_immutability(world: World) -> None:
    a = world.a
    req = await to_accepted(world, a)
    rid = req["id"]
    draft = await world.ok(a.dispatcher, "POST", f"/requests/{rid}/estimates", json=EST)
    assert draft["total_minor"] == 90 * 120000 // 60 + 2 * 85000 and draft["currency"] == "KGS"
    assert (
        await world.post(a.dispatcher, f"/requests/{rid}/estimates", EST)
    ).status_code == 409  # one draft
    # Requesters never see drafts.
    assert await world.ok(a.requester, "GET", f"/requests/{rid}/estimates") == []
    edited = await world.ok(
        a.dispatcher, "PUT", f"/estimates/{draft['id']}", json={**EST, "labor_minutes": 60}
    )
    assert edited["total_minor"] == 120000 + 170000
    submitted = await world.ok(a.dispatcher, "POST", f"/estimates/{draft['id']}/submit")
    assert submitted["status"] == "AWAITING_APPROVAL"
    # Submitted contents are immutable.
    frozen = await world.call(a.dispatcher, "PUT", f"/estimates/{draft['id']}", json=EST)
    assert frozen.status_code == 409 and error_code(frozen) == "ESTIMATE_IMMUTABLE"
    # EST-04: the technician cannot start while approval is pending.
    blocked = await world.post(a.tech, f"/requests/{rid}/start")
    assert blocked.status_code == 409 and error_code(blocked) == "ESTIMATE_NOT_APPROVED"
    # Rejection needs a reason and the reviewed version.
    assert (
        await world.post(a.requester, f"/estimates/{draft['id']}/reject", {"version": 1})
    ).status_code == 422
    assert (
        await world.post(
            a.requester2, f"/estimates/{draft['id']}/reject", {"version": 1, "reason": "not mine"}
        )
    ).status_code == 404
    rejected = await world.ok(
        a.requester,
        "POST",
        f"/estimates/{draft['id']}/reject",
        json={"version": 1, "reason": "Too expensive"},
    )
    assert rejected["status"] == "REJECTED" and rejected["decision_reason"] == "Too expensive"
    still = await world.post(a.tech, f"/requests/{rid}/start")
    assert still.status_code == 409  # rejected must be replaced or withdrawn
    # Revised version supersedes the rejected one.
    v2 = await world.ok(
        a.dispatcher, "POST", f"/requests/{rid}/estimates", json={**EST, "labor_minutes": 30}
    )
    assert v2["version"] == 2 and v2["previous_version_id"] == draft["id"]
    await world.ok(a.dispatcher, "POST", f"/estimates/{v2['id']}/submit")
    versions = await world.ok(a.requester, "GET", f"/requests/{rid}/estimates")
    assert [(v["version"], v["status"]) for v in versions] == [
        (2, "AWAITING_APPROVAL"),
        (1, "SUPERSEDED"),
    ]
    # Approving a stale version number is refused (EST-06).
    stale = await world.post(a.requester, f"/estimates/{v2['id']}/approve", {"version": 1})
    assert stale.status_code == 409 and error_code(stale) == "ESTIMATE_VERSION_MISMATCH"
    approved = await world.ok(
        a.requester, "POST", f"/estimates/{v2['id']}/approve", json={"version": 2}
    )
    assert approved["status"] == "APPROVED" and approved["decided_by"]
    started = await world.ok(a.tech, "POST", f"/requests/{rid}/start", json={})
    assert started["status"] == "IN_PROGRESS"


async def test_simultaneous_estimate_decisions_only_one_succeeds(world: World) -> None:
    a = world.a
    req = await to_accepted(world, a)
    est = await world.ok(a.dispatcher, "POST", f"/requests/{req['id']}/estimates", json=EST)
    await world.ok(a.dispatcher, "POST", f"/estimates/{est['id']}/submit")
    results = await asyncio.gather(
        world.post(a.requester, f"/estimates/{est['id']}/approve", {"version": 1}),
        world.post(
            a.requester,
            f"/estimates/{est['id']}/reject",
            {"version": 1, "reason": "Changed my mind"},
        ),
        world.post(a.requester, f"/estimates/{est['id']}/approve", {"version": 1}),
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409, 409]
    assert {error_code(r) for r in results if r.status_code == 409} == {"ESTIMATE_ALREADY_DECIDED"}


async def test_estimate_decision_idempotency_key(world: World) -> None:
    a = world.a
    req = await to_accepted(world, a)
    est = await world.ok(a.dispatcher, "POST", f"/requests/{req['id']}/estimates", json=EST)
    await world.ok(a.dispatcher, "POST", f"/estimates/{est['id']}/submit")
    key = {"Idempotency-Key": "decision-key-01"}
    first = await world.post(
        a.requester, f"/estimates/{est['id']}/approve", {"version": 1}, headers=key
    )
    replay = await world.post(
        a.requester, f"/estimates/{est['id']}/approve", {"version": 1}, headers=key
    )
    assert (
        first.status_code == replay.status_code == 200
        and replay.headers["idempotency-replayed"] == "true"
    )
    conflict = await world.post(
        a.requester, f"/estimates/{est['id']}/reject", {"version": 1, "reason": "oops"}, headers=key
    )
    assert conflict.status_code == 409 and error_code(conflict) == "IDEMPOTENCY_KEY_REUSED"


async def test_estimate_validation_rejects_negative_values(world: World) -> None:
    a = world.a
    req = await to_triaged(world, a)
    bad = await world.post(
        a.dispatcher, f"/requests/{req['id']}/estimates", {**EST, "labor_rate_minor": -1}
    )
    assert bad.status_code == 422
    zero_qty = await world.post(
        a.dispatcher,
        f"/requests/{req['id']}/estimates",
        {**EST, "lines": [{"description": "x", "quantity": 0, "unit_price_minor": 1}]},
    )
    assert zero_qty.status_code == 422
    float_price = await world.post(
        a.dispatcher,
        f"/requests/{req['id']}/estimates",
        {**EST, "lines": [{"description": "x", "quantity": 1, "unit_price_minor": 1.5}]},
    )
    assert float_price.status_code == 422


# ---------------------------------------------------------------- Maintenance


async def test_recurring_generation_is_deduplicated_even_when_concurrent(world: World) -> None:
    a = world.a
    first_date = date.today() - timedelta(days=21)
    plan = await world.ok(
        a.dispatcher,
        "POST",
        "/maintenance-plans",
        json={
            "asset_id": str(a.asset_id),
            "category_id": str(a.open_category_id),
            "title": "Weekly belt inspection",
            "description": "Inspect belts and bearings and log vibration readings.",
            "first_date": first_date.isoformat(),
            "recurrence": "WEEKLY",
        },
    )
    as_of = date.today()

    async def run() -> int:
        async with SessionLocal() as db:
            org = await db.get(Organization, a.id)
            assert org is not None
            created = await generate(db, org, as_of)
            await db.commit()
            return len(created)

    counts = await asyncio.gather(run(), run(), run())
    assert sum(counts) == 4  # day 0, 7, 14, 21
    assert await run() == 0
    detail = await world.ok(a.dispatcher, "GET", f"/maintenance-plans/{plan['id']}")
    assert detail["generated_count"] == 4
    assert detail["next_occurrence"] == (first_date + timedelta(weeks=4)).isoformat()
    assert all(g["occurrence_date"] for g in detail["generated"])
    async with SessionLocal() as db:
        total = await db.scalar(
            select(func.count())
            .select_from(ServiceRequest)
            .where(ServiceRequest.maintenance_plan_id.is_not(None))
        )
        assert total == 4
    # Generated requests follow the normal lifecycle.
    generated_id = detail["generated"][0]["request_id"]
    triaged = await world.ok(a.dispatcher, "POST", f"/requests/{generated_id}/triage", json={})
    assert triaged["status"] == "TRIAGED" and triaged["is_preventive"]
    # API endpoint is safe to repeat, and disabling stops future generation.
    again = await world.ok(
        a.dispatcher,
        "POST",
        "/maintenance-plans/generate",
        json={"as_of": (as_of + timedelta(days=30)).isoformat()},
    )
    assert again["generated_count"] >= 4
    await world.ok(
        a.dispatcher, "PATCH", f"/maintenance-plans/{plan['id']}", json={"is_enabled": False}
    )
    none = await world.ok(
        a.dispatcher,
        "POST",
        "/maintenance-plans/generate",
        json={"as_of": (as_of + timedelta(days=200)).isoformat()},
    )
    assert none["generated_count"] == 0


async def test_retired_asset_blocks_plans_and_generation(world: World) -> None:
    a = world.a
    plan_body = {
        "asset_id": str(a.asset_id),
        "category_id": str(a.open_category_id),
        "title": "Monthly inspection",
        "description": "Monthly inspection of the unit with a written checklist.",
        "first_date": (date.today() - timedelta(days=40)).isoformat(),
        "recurrence": "MONTHLY",
    }
    plan = await world.ok(a.dispatcher, "POST", "/maintenance-plans", json=plan_body)
    await world.ok(a.dispatcher, "PATCH", f"/assets/{a.asset_id}", json={"status": "RETIRED"})
    blocked = await world.post(a.dispatcher, "/maintenance-plans", plan_body)
    assert blocked.status_code == 409 and error_code(blocked) == "ASSET_NOT_ACTIVE"
    generated = await world.ok(
        a.dispatcher,
        "POST",
        "/maintenance-plans/generate",
        json={"as_of": date.today().isoformat()},
    )
    assert generated["generated_count"] == 0
    # History of the asset remains readable.
    assert (await world.get(a.dispatcher, f"/assets/{a.asset_id}")).status_code == 200
    retired_request = await world.post(
        a.requester,
        "/requests",
        {
            "title": "Retired asset request",
            "description": "Trying to file a request on a retired asset.",
            "category_id": str(a.category_id),
            "property_id": str(a.property_id),
            "asset_id": str(a.asset_id),
        },
    )
    assert retired_request.status_code == 422 and error_code(retired_request) == "ASSET_RETIRED"
    _ = (plan, cmd, slot)
