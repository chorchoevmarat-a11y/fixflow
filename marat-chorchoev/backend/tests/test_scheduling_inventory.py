"""Scheduling overlap + races, notes/material idempotency, inventory concurrency."""

import asyncio

from sqlalchemy import delete, func, select

from app.database import SessionLocal
from app.models.models import Assignment, InventoryItem, MaterialUsage, WorkNote
from tests.conftest import World
from tests.helpers import (
    cmd,
    create_request,
    error_code,
    slot,
    to_in_progress,
    to_scheduled,
    to_triaged,
)


async def test_overlap_is_rejected_but_adjacent_slots_are_allowed(world: World) -> None:
    a = world.a
    await to_scheduled(world, a, when=slot(hour=10, minutes=60))  # 10:00-11:00
    overlapping = await to_triaged(world, a)
    body = {"technician_id": str(a.tech.technician_id), **slot(hour=10, minutes=60)}
    clash = await world.post(a.dispatcher, f"/requests/{overlapping['id']}/assign", body)
    assert clash.status_code == 409 and error_code(clash) == "SCHEDULE_CONFLICT"
    # 11:00-12:00 touches but does not overlap [10:00, 11:00).
    ok = await world.post(
        a.dispatcher,
        f"/requests/{overlapping['id']}/assign",
        {"technician_id": str(a.tech.technician_id), **slot(hour=11, minutes=60)},
    )
    assert ok.status_code == 200
    # Partial overlap from the other side.
    third = await to_triaged(world, a)
    partial = await world.post(
        a.dispatcher,
        f"/requests/{third['id']}/assign",
        {"technician_id": str(a.tech.technician_id), **slot(hour=10, minutes=90)},
    )
    assert partial.status_code == 409


async def test_candidates_explain_why_not(world: World) -> None:
    a = world.a
    await to_scheduled(world, a, when=slot(hour=10))
    req = await to_triaged(world, a)
    window = slot(hour=10)
    result = await world.ok(a.dispatcher, "GET", f"/requests/{req['id']}/candidates", params=window)
    by_id = {c["technician_id"]: c for c in result["candidates"]}
    busy = by_id[str(a.tech.technician_id)]
    assert not busy["eligible"] and busy["reasons"][0]["code"] == "SCHEDULE_CONFLICT"
    assert by_id[str(a.tech2.technician_id)]["eligible"]
    outside = await world.ok(
        a.dispatcher, "GET", f"/requests/{req['id']}/candidates", params=slot(hour=19)
    )
    assert {r["code"] for r in outside["candidates"][0]["reasons"]} >= {"OUTSIDE_AVAILABILITY"}


async def test_missing_skill_and_past_slot_are_rejected(world: World) -> None:
    a = world.a
    from app.models.models import TechnicianSkill

    async with SessionLocal() as db:
        await db.execute(
            delete(TechnicianSkill).where(TechnicianSkill.technician_id == a.tech2.technician_id)
        )
        await db.commit()
    req = await to_triaged(world, a)
    unskilled = await world.post(
        a.dispatcher,
        f"/requests/{req['id']}/assign",
        {"technician_id": str(a.tech2.technician_id), **slot()},
    )
    assert unskilled.status_code == 422 and error_code(unskilled) == "TECHNICIAN_NOT_ELIGIBLE"
    past = await world.post(
        a.dispatcher,
        f"/requests/{req['id']}/assign",
        {
            "technician_id": str(a.tech.technician_id),
            "start_at": "2020-01-06T05:00:00+00:00",
            "end_at": "2020-01-06T07:00:00+00:00",
        },
    )
    assert past.status_code == 422 and error_code(past) == "SLOT_IN_PAST"
    short = await world.post(
        a.dispatcher,
        f"/requests/{req['id']}/assign",
        {"technician_id": str(a.tech.technician_id), **slot(minutes=20)},
    )
    assert short.status_code == 422 and error_code(short) == "SLOT_TOO_SHORT"


async def test_concurrent_assignments_exactly_one_wins(world: World) -> None:
    a = world.a
    requests = [await to_triaged(world, a, title=f"Concurrent job number {i}") for i in range(6)]
    when = slot(hour=13)
    results = await asyncio.gather(
        *[
            world.post(
                a.dispatcher,
                f"/requests/{r['id']}/assign",
                {"technician_id": str(a.tech.technician_id), **when},
            )
            for r in requests
        ]
    )
    codes = sorted(r.status_code for r in results)
    assert codes == [200] + [409] * 5
    assert all(error_code(r) == "SCHEDULE_CONFLICT" for r in results if r.status_code == 409)
    async with SessionLocal() as db:
        active = await db.scalar(
            select(func.count()).select_from(Assignment).where(Assignment.is_active)
        )
        assert active == 1


async def test_note_replay_is_idempotent_and_key_reuse_conflicts(world: World) -> None:
    a = world.a
    req = await to_in_progress(world, a)
    rid = req["id"]
    command = cmd()
    payload = {"body": "Replaced the fuse.", "client_command_id": command}
    first = await world.post(a.tech, f"/requests/{rid}/notes", payload)
    second = await world.post(a.tech, f"/requests/{rid}/notes", payload)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    different = await world.post(
        a.tech, f"/requests/{rid}/notes", {"body": "Something else", "client_command_id": command}
    )
    assert different.status_code == 409 and error_code(different) == "COMMAND_ID_REUSED"
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(WorkNote)) == 1
    # Concurrent duplicates still produce one note.
    command2 = cmd()
    payload2 = {"body": "Concurrent duplicate", "client_command_id": command2}
    both = await asyncio.gather(
        *[world.post(a.tech, f"/requests/{rid}/notes", payload2) for _ in range(4)]
    )
    assert sorted(r.status_code for r in both) == [200, 200, 200, 201]
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(WorkNote)) == 2


async def test_offline_note_after_reassignment_is_a_conflict(world: World) -> None:
    a = world.a
    req = await to_scheduled(world, a)
    rid = req["id"]
    assignment_id = req["assignment"]["id"]
    await world.ok(
        a.dispatcher,
        "POST",
        f"/requests/{rid}/reschedule",
        json={"technician_id": str(a.tech2.technician_id), **slot(weekday=2)},
    )
    stale = await world.post(
        a.tech,
        f"/requests/{rid}/notes",
        {"body": "Written offline", "client_command_id": cmd(), "assignment_id": assignment_id},
    )
    assert stale.status_code == 409 and error_code(stale) == "ASSIGNMENT_REVOKED"
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(WorkNote)) == 0


async def test_material_consumption_is_atomic_replay_safe_and_snapshots_price(world: World) -> None:
    a = world.a
    req = await to_in_progress(world, a)
    rid = req["id"]
    command = cmd()
    body = {"item_id": str(a.item_id), "quantity": 4, "client_command_id": command}
    first = await world.post(a.tech, f"/requests/{rid}/materials", body)
    replay = await world.post(a.tech, f"/requests/{rid}/materials", body)
    assert first.status_code == 201 and replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    changed = await world.post(a.tech, f"/requests/{rid}/materials", {**body, "quantity": 5})
    assert changed.status_code == 409 and error_code(changed) == "COMMAND_ID_REUSED"
    async with SessionLocal() as db:
        item = await db.get(InventoryItem, a.item_id)
        assert item is not None and item.stock_quantity == 6
    # Raising the price later does not change the recorded snapshot.
    await world.ok(a.admin, "PATCH", f"/inventory/{a.item_id}", json={"unit_price_minor": 999999})
    usage = (await world.ok(a.dispatcher, "GET", f"/requests/{rid}/materials"))[0]
    assert usage["unit_price_minor"] == 85000 and usage["total_minor"] == 4 * 85000
    # Technicians do not see money fields.
    tech_view = (await world.ok(a.tech, "GET", f"/requests/{rid}/materials"))[0]
    assert "unit_price_minor" not in tech_view


async def test_inventory_race_never_goes_negative(world: World) -> None:
    a = world.a
    first = await to_in_progress(world, a, when=slot(hour=9))
    second = await to_in_progress(world, a, tech=a.tech2, when=slot(hour=9))
    attempts = await asyncio.gather(
        world.post(
            a.tech,
            f"/requests/{first['id']}/materials",
            {"item_id": str(a.item_id), "quantity": 7, "client_command_id": cmd()},
        ),
        world.post(
            a.tech2,
            f"/requests/{second['id']}/materials",
            {"item_id": str(a.item_id), "quantity": 7, "client_command_id": cmd()},
        ),
    )
    assert sorted(r.status_code for r in attempts) == [201, 409]
    loser = next(r for r in attempts if r.status_code == 409)
    assert error_code(loser) == "INSUFFICIENT_STOCK"
    async with SessionLocal() as db:
        item = await db.get(InventoryItem, a.item_id)
        assert item is not None and item.stock_quantity == 3
        assert await db.scalar(select(func.count()).select_from(MaterialUsage)) == 1


async def test_materials_need_in_progress_and_assignment(world: World) -> None:
    a = world.a
    scheduled = await to_scheduled(world, a)
    early = await world.post(
        a.tech,
        f"/requests/{scheduled['id']}/materials",
        {"item_id": str(a.item_id), "quantity": 1, "client_command_id": cmd()},
    )
    assert early.status_code == 409
    working = await to_in_progress(world, a, when=slot(hour=14))
    other = await world.post(
        a.tech2,
        f"/requests/{working['id']}/materials",
        {"item_id": str(a.item_id), "quantity": 1, "client_command_id": cmd()},
    )
    assert other.status_code == 404
    foreign_item = await world.post(
        a.tech,
        f"/requests/{working['id']}/materials",
        {"item_id": str(world.b.item_id), "quantity": 1, "client_command_id": cmd()},
    )
    assert foreign_item.status_code == 404


async def test_stock_addition_and_low_stock(world: World) -> None:
    a = world.a
    low = await world.ok(a.admin, "GET", "/inventory?low_stock=true")
    assert low["total"] == 0
    await world.ok(a.admin, "PATCH", f"/inventory/{a.item_id}", json={"reorder_threshold": 10})
    low = await world.ok(a.admin, "GET", "/inventory?low_stock=true")
    assert low["total"] == 1 and low["items"][0]["is_low_stock"]
    added = await world.ok(
        a.admin,
        "POST",
        f"/inventory/{a.item_id}/stock-additions",
        json={"quantity": 5, "reason": "Supplier delivery"},
    )
    assert added["stock_quantity"] == 15 and not added["is_low_stock"]
    assert (
        await world.post(
            a.admin, f"/inventory/{a.item_id}/stock-additions", {"quantity": 0, "reason": "zero"}
        )
    ).status_code == 422
    assert (
        await world.post(
            a.dispatcher, f"/inventory/{a.item_id}/stock-additions", {"quantity": 1, "reason": "no"}
        )
    ).status_code == 403
    movements = await world.ok(a.admin, "GET", f"/inventory/{a.item_id}/movements")
    assert movements["total"] == 1 and movements["items"][0]["reason"] == "Supplier delivery"


async def test_assign_endpoint_idempotency(world: World) -> None:
    a = world.a
    req = await to_triaged(world, a)
    body = {"technician_id": str(a.tech.technician_id), **slot(hour=15)}
    key = {"Idempotency-Key": "assign-key-0001"}
    first = await world.post(a.dispatcher, f"/requests/{req['id']}/assign", body, headers=key)
    replay = await world.post(a.dispatcher, f"/requests/{req['id']}/assign", body, headers=key)
    assert first.status_code == 200 and replay.status_code == 200
    assert replay.headers["idempotency-replayed"] == "true" and replay.json() == first.json()
    mismatch = await world.post(
        a.dispatcher,
        f"/requests/{req['id']}/assign",
        {**body, "technician_id": str(a.tech2.technician_id)},
        headers=key,
    )
    assert mismatch.status_code == 409 and error_code(mismatch) == "IDEMPOTENCY_KEY_REUSED"
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Assignment)) == 1
    _ = create_request  # keep helper import used


async def test_smart_slot_suggestions_are_bookable(world: World) -> None:
    a = world.a
    await to_scheduled(world, a, when=slot(hour=10))
    req = await to_triaged(world, a)
    result = await world.ok(a.dispatcher, "GET", f"/requests/{req['id']}/suggestions")
    assert result["options"], "expected at least one suggestion"
    # Every suggestion is accepted by the real assignment endpoint.
    best = result["options"][0]
    booked = await world.post(
        a.dispatcher,
        f"/requests/{req['id']}/assign",
        {
            "technician_id": best["technician_id"],
            "start_at": best["start_at"],
            "end_at": best["end_at"],
        },
    )
    assert booked.status_code == 200
    # Suggestions only exist for triaged requests.
    again = await world.get(a.dispatcher, f"/requests/{req['id']}/suggestions")
    assert again.status_code == 409
