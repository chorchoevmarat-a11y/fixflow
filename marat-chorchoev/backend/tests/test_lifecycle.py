"""Request lifecycle, permissions, and audit (LIFE-01..09, E2E-01)."""

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.models import AssetServiceHistory, Assignment, AuditEvent, Notification
from tests.conftest import World
from tests.helpers import (
    cmd,
    create_request,
    error_code,
    request_body,
    slot,
    to_accepted,
    to_completed,
    to_in_progress,
    to_scheduled,
    to_triaged,
    upload,
)


async def test_request_to_closure_happy_path(world: World) -> None:
    a = world.a
    req = await create_request(world, a)
    assert req["status"] == "SUBMITTED"
    assert req["reference"] == "REQ-00001"
    rid = req["id"]

    req = await world.ok(
        a.dispatcher, "POST", f"/requests/{rid}/triage", json={"triage_notes": "Looks urgent"}
    )
    assert req["status"] == "TRIAGED" and "assign" in req["allowed_actions"]

    body = {"technician_id": str(a.tech.technician_id), **slot()}
    req = await world.ok(a.dispatcher, "POST", f"/requests/{rid}/assign", json=body)
    assert req["status"] == "SCHEDULED"
    assert req["assignment"]["technician_id"] == str(a.tech.technician_id)

    req = await world.ok(a.tech, "POST", f"/requests/{rid}/accept", json={})
    assert req["status"] == "ACCEPTED" and "start" in req["allowed_actions"]
    req = await world.ok(a.tech, "POST", f"/requests/{rid}/start", json={})
    assert req["status"] == "IN_PROGRESS"

    note = await world.post(
        a.tech, f"/requests/{rid}/notes", {"body": "Belt is worn out.", "client_command_id": cmd()}
    )
    assert note.status_code == 201
    assert (await upload(world, a.tech, rid, "COMPLETION")).status_code == 201
    req = await world.ok(
        a.tech,
        "POST",
        f"/requests/{rid}/complete",
        json={"completion_note": "Replaced the fan belt and verified airflow."},
    )
    assert req["status"] == "COMPLETED"
    assert req["sla"]["stopped_at"] is not None

    req = await world.ok(a.requester, "POST", f"/requests/{rid}/close", json={})
    assert req["status"] == "CLOSED" and req["allowed_actions"] == ["give_feedback"]
    req = await world.ok(
        a.requester, "POST", f"/requests/{rid}/feedback", json={"rating": 5, "comment": "Great"}
    )
    assert req["feedback"]["rating"] == 5

    # Every transition is in the activity timeline, in order, with its actor.
    activity = await world.ok(a.dispatcher, "GET", f"/requests/{rid}/activity?page_size=100")
    actions = [event["action"] for event in activity["items"]]
    for expected in (
        "request.created",
        "request.triaged",
        "request.assigned",
        "request.accepted",
        "request.started",
        "request.completed",
        "request.closed",
        "request.feedback",
    ):
        assert expected in actions
    assert (
        actions.index("request.triaged")
        < actions.index("request.assigned")
        < actions.index("request.completed")
    )

    async with SessionLocal() as db:
        # Asset history and the dashboard reflect the completed job.
        assert await db.scalar(select(func.count()).select_from(AssetServiceHistory)) == 1
    dashboard = await world.ok(a.dispatcher, "GET", "/reports/dashboard")
    assert dashboard["status_counts"]["CLOSED"] == 1
    assert dashboard["completed_in_range"] == 1


async def test_validation_is_enforced_by_the_server(world: World) -> None:
    a = world.a
    short = await world.post(
        a.requester, "/requests", request_body(a, title="Hey", description="too short")
    )
    assert short.status_code == 422
    fields = {f["field"] for f in short.json()["error"]["details"]["fields"]}
    assert {"title", "description"} <= fields
    missing = await world.post(a.requester, "/requests", {"title": "A valid title"})
    assert missing.status_code == 422
    bad_priority = await world.post(a.requester, "/requests", request_body(a, priority="URGENT"))
    assert bad_priority.status_code == 422


async def test_role_permissions_on_transitions(world: World) -> None:
    a = world.a
    req = await create_request(world, a)
    rid = req["id"]
    # Only dispatcher/admin triage.
    assert (await world.post(a.requester, f"/requests/{rid}/triage")).status_code == 403
    assert (await world.post(a.tech, f"/requests/{rid}/triage")).status_code in (403, 404)
    await world.ok(a.dispatcher, "POST", f"/requests/{rid}/triage", json={})
    # A requester cannot assign.
    body = {"technician_id": str(a.tech.technician_id), **slot()}
    assert (await world.post(a.requester, f"/requests/{rid}/assign", body)).status_code == 403
    await world.ok(a.admin, "POST", f"/requests/{rid}/assign", json=body)
    # Only the *assigned* technician may accept; another technician cannot even see it.
    other = await world.post(a.tech2, f"/requests/{rid}/accept")
    assert other.status_code == 404
    assert (await world.post(a.dispatcher, f"/requests/{rid}/accept")).status_code == 403
    await world.ok(a.tech, "POST", f"/requests/{rid}/accept", json={})
    # Staff cannot start work on the technician's behalf.
    assert (await world.post(a.dispatcher, f"/requests/{rid}/start")).status_code == 403


async def test_requesters_only_see_their_own_requests(world: World) -> None:
    a = world.a
    mine = await create_request(world, a)
    theirs = await create_request(
        world, a, requester=a.requester2, title="Another person's request"
    )
    listing = await world.ok(a.requester, "GET", "/requests")
    assert [item["id"] for item in listing["items"]] == [mine["id"]]
    assert (await world.get(a.requester, f"/requests/{theirs['id']}")).status_code == 404
    assert (await world.post(a.requester, f"/requests/{theirs['id']}/cancel")).status_code == 404
    # Staff see both.
    assert (await world.ok(a.dispatcher, "GET", "/requests"))["total"] == 2


async def test_invalid_transitions_return_conflict(world: World) -> None:
    a = world.a
    req = await create_request(world, a)
    rid = req["id"]
    # SUBMITTED cannot be assigned, closed, or reopened.
    assign = await world.post(
        a.dispatcher,
        f"/requests/{rid}/assign",
        {"technician_id": str(a.tech.technician_id), **slot()},
    )
    assert assign.status_code == 409 and error_code(assign) == "INVALID_TRANSITION"
    assert (await world.post(a.requester, f"/requests/{rid}/close")).status_code == 409
    assert (
        await world.post(a.requester, f"/requests/{rid}/reopen", {"reason": "no reason"})
    ).status_code == 409
    await world.ok(a.dispatcher, "POST", f"/requests/{rid}/triage", json={})
    # Triage twice is rejected.
    assert (await world.post(a.dispatcher, f"/requests/{rid}/triage")).status_code == 409


async def test_technician_decline_returns_to_triaged_and_keeps_history(world: World) -> None:
    a = world.a
    req = await to_scheduled(world, a)
    rid = req["id"]
    first_assignment = req["assignment"]["id"]
    assert (
        await world.post(a.tech, f"/requests/{rid}/decline", {})
    ).status_code == 422  # reason required
    declined = await world.ok(
        a.tech, "POST", f"/requests/{rid}/decline", json={"reason": "Off sick that day"}
    )
    assert declined["status"] == "TRIAGED"
    # The slot is released: another request can take the same technician and time.
    again = await world.ok(
        a.dispatcher,
        "POST",
        f"/requests/{rid}/assign",
        json={"technician_id": str(a.tech2.technician_id), **slot()},
    )
    assert again["status"] == "SCHEDULED" and again["assignment"]["id"] != first_assignment
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Assignment.status, Assignment.is_active).order_by(Assignment.created_at)
            )
        ).all()
        assert [tuple(r) for r in rows] == [("DECLINED", False), ("SCHEDULED", True)]
        declined_notifications = await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type == "ASSIGNMENT_DECLINED")
        )
        assert declined_notifications == 2  # admin + dispatcher
    # The technician who declined lost access to the job.
    assert (await world.get(a.tech, f"/requests/{rid}")).status_code == 404


async def test_unassign_and_reschedule_before_work_begins(world: World) -> None:
    a = world.a
    req = await to_accepted(world, a)
    rid = req["id"]
    moved = await world.ok(
        a.dispatcher,
        "POST",
        f"/requests/{rid}/reschedule",
        json={
            "technician_id": str(a.tech.technician_id),
            **slot(weekday=2),
            "reason": "Customer asked",
        },
    )
    assert moved["status"] == "SCHEDULED"  # must be accepted again
    back = await world.ok(
        a.dispatcher, "POST", f"/requests/{rid}/unassign", json={"reason": "Need a specialist"}
    )
    assert back["status"] == "TRIAGED" and back["assignment"] is None
    async with SessionLocal() as db:
        statuses = list(await db.scalars(select(Assignment.status).order_by(Assignment.created_at)))
        assert statuses == ["RESCHEDULED", "UNASSIGNED"]
    # Once work has started, staff can no longer unassign.
    started = await to_in_progress(world, a, when=slot(weekday=3))
    late = await world.post(
        a.dispatcher, f"/requests/{started['id']}/unassign", {"reason": "too late"}
    )
    assert late.status_code == 409


async def test_block_and_unblock_require_text(world: World) -> None:
    a = world.a
    req = await to_in_progress(world, a)
    rid = req["id"]
    assert (await world.post(a.tech, f"/requests/{rid}/block", {})).status_code == 422
    blocked = await world.ok(
        a.tech, "POST", f"/requests/{rid}/block", json={"reason": "Waiting for parts"}
    )
    assert blocked["status"] == "BLOCKED" and blocked["blocker_reason"] == "Waiting for parts"
    # Cannot complete while blocked.
    assert (
        await world.post(a.tech, f"/requests/{rid}/complete", {"completion_note": "x" * 30})
    ).status_code == 409
    assert (await world.post(a.tech, f"/requests/{rid}/unblock", {})).status_code == 422
    resumed = await world.ok(
        a.tech, "POST", f"/requests/{rid}/unblock", json={"resolution_note": "Part arrived"}
    )
    assert resumed["status"] == "IN_PROGRESS"


async def test_completion_requires_note_and_evidence(world: World) -> None:
    a = world.a
    req = await to_in_progress(world, a)
    rid = req["id"]
    short = await world.post(a.tech, f"/requests/{rid}/complete", {"completion_note": "Done"})
    assert short.status_code == 422
    no_image = await world.post(
        a.tech, f"/requests/{rid}/complete", {"completion_note": "Replaced the belt and tested."}
    )
    assert no_image.status_code == 422 and error_code(no_image) == "COMPLETION_EVIDENCE_REQUIRED"
    assert (await upload(world, a.tech, rid, "COMPLETION")).status_code == 201
    done = await world.ok(
        a.tech,
        "POST",
        f"/requests/{rid}/complete",
        json={"completion_note": "Replaced the belt and tested."},
    )
    assert done["status"] == "COMPLETED"


async def test_completion_rolls_back_when_material_validation_fails(world: World) -> None:
    a = world.a
    req = await to_in_progress(world, a)
    rid = req["id"]
    assert (await upload(world, a.tech, rid, "COMPLETION")).status_code == 201
    failed = await world.post(
        a.tech,
        f"/requests/{rid}/complete",
        {
            "completion_note": "Replaced filters throughout the unit.",
            "materials": [
                {"item_id": str(a.item_id), "quantity": 4, "client_command_id": cmd()},
                {"item_id": str(a.item_id), "quantity": 50, "client_command_id": cmd()},
            ],
        },
    )
    assert failed.status_code == 409 and error_code(failed) == "INSUFFICIENT_STOCK"
    # Nothing was applied: still in progress, stock untouched, no usage rows.
    assert (await world.ok(a.tech, "GET", f"/requests/{rid}"))["status"] == "IN_PROGRESS"
    assert await world.ok(a.tech, "GET", f"/requests/{rid}/materials") == []
    items = await world.ok(a.admin, "GET", "/inventory")
    assert items["items"][0]["stock_quantity"] == 10


async def test_rework_cycle(world: World) -> None:
    a = world.a
    req = await to_completed(world, a)
    rid = req["id"]
    assert (await world.post(a.requester, f"/requests/{rid}/reopen", {})).status_code == 422
    reopened = await world.ok(
        a.requester, "POST", f"/requests/{rid}/reopen", json={"reason": "Still noisy"}
    )
    assert reopened["status"] == "REOPENED"
    # A dispatcher must triage the rework before it can be scheduled again.
    direct = await world.post(
        a.dispatcher,
        f"/requests/{rid}/assign",
        {"technician_id": str(a.tech.technician_id), **slot(weekday=1)},
    )
    assert direct.status_code == 409
    triaged = await world.ok(a.dispatcher, "POST", f"/requests/{rid}/triage", json={})
    assert triaged["status"] == "TRIAGED"


async def test_cancel_rules_and_terminal_states(world: World) -> None:
    a = world.a
    submitted = await create_request(world, a)
    canceled = await world.ok(a.requester, "POST", f"/requests/{submitted['id']}/cancel", json={})
    assert canceled["status"] == "CANCELED" and canceled["allowed_actions"] == []
    # Terminal: nothing moves it again.
    assert (
        await world.post(a.dispatcher, f"/requests/{submitted['id']}/triage")
    ).status_code == 409

    triaged = await to_triaged(world, a)
    # A requester may only cancel while SUBMITTED.
    assert (await world.post(a.requester, f"/requests/{triaged['id']}/cancel")).status_code == 409
    # Staff need a reason.
    assert (
        await world.post(a.dispatcher, f"/requests/{triaged['id']}/cancel", {})
    ).status_code == 422

    scheduled = await to_scheduled(world, a)
    done = await world.ok(
        a.dispatcher, "POST", f"/requests/{scheduled['id']}/cancel", json={"reason": "Site closed"}
    )
    assert done["status"] == "CANCELED"
    async with SessionLocal() as db:
        assert list(await db.scalars(select(Assignment.status))) == ["CANCELED"]

    accepted = await to_accepted(world, a, when=slot(weekday=1))
    late = await world.post(
        a.dispatcher, f"/requests/{accepted['id']}/cancel", {"reason": "too late"}
    )
    assert late.status_code == 409


async def test_staff_close_needs_reason_and_technician_cannot_close(world: World) -> None:
    a = world.a
    req = await to_completed(world, a)
    rid = req["id"]
    assert (await world.post(a.tech, f"/requests/{rid}/close")).status_code == 403
    assert (await world.post(a.dispatcher, f"/requests/{rid}/close", {})).status_code == 422
    closed = await world.ok(
        a.dispatcher, "POST", f"/requests/{rid}/close", json={"reason": "Requester unreachable"}
    )
    assert closed["status"] == "CLOSED"


async def test_reclassify_requires_reason_and_is_audited(world: World) -> None:
    a = world.a
    req = await create_request(world, a, priority="LOW")
    rid = req["id"]
    assert (
        await world.post(a.dispatcher, f"/requests/{rid}/reclassify", {"priority": "HIGH"})
    ).status_code == 422
    updated = await world.ok(
        a.dispatcher,
        "POST",
        f"/requests/{rid}/reclassify",
        json={"priority": "HIGH", "reason": "Safety risk"},
    )
    assert updated["priority"] == "HIGH" and updated["sla"]["budget_seconds"] == 8 * 3600
    async with SessionLocal() as db:
        event = (
            await db.execute(
                select(AuditEvent).where(AuditEvent.action == "request.priority_changed")
            )
        ).scalar_one()
        assert event.before is not None and event.after is not None
        assert event.before["priority"] == "LOW" and event.after["reason"] == "Safety risk"


async def test_duplicate_link_is_kept(world: World) -> None:
    a = world.a
    original = await create_request(world, a)
    dup = await create_request(world, a, title="Same noise again")
    linked = await world.ok(
        a.dispatcher,
        "POST",
        f"/requests/{dup['id']}/duplicate",
        json={"duplicate_of_id": original["id"]},
    )
    assert linked["duplicate_of"]["id"] == original["id"]
    itself = await world.post(
        a.dispatcher, f"/requests/{dup['id']}/duplicate", {"duplicate_of_id": dup["id"]}
    )
    assert itself.status_code == 422


async def test_disabled_category_and_unauthorized_property_are_rejected(world: World) -> None:
    a = world.a
    await world.ok(
        a.admin, "PATCH", f"/categories/{a.open_category_id}", json={"is_enabled": False}
    )
    disabled = await world.post(
        a.requester, "/requests", request_body(a, category_id=str(a.open_category_id))
    )
    assert disabled.status_code == 422 and error_code(disabled) == "CATEGORY_DISABLED"
    # A restricted property is usable only by the listed requester.
    restricted = await world.ok(
        a.dispatcher,
        "POST",
        "/properties",
        json={
            "name": "Vault",
            "address": "9 Secret Street",
            "is_shared": False,
            "requester_membership_ids": [str(a.requester2.membership_id)],
        },
    )
    body = request_body(a, property_id=restricted["id"], asset_id=None)
    denied = await world.post(a.requester, "/requests", body)
    assert denied.status_code == 422 and error_code(denied) == "PROPERTY_NOT_ALLOWED"
    assert (await world.post(a.requester2, "/requests", body)).status_code == 201
    # An asset from a different property is rejected too.
    mismatch = await world.post(
        a.requester2, "/requests", request_body(a, property_id=restricted["id"])
    )
    assert mismatch.status_code == 422 and error_code(mismatch) == "ASSET_NOT_ALLOWED"
