"""Cross-organization denial (SEC-01, E2E-09) and protected files (COMM-05/06)."""

from app.config import settings
from tests.conftest import World
from tests.helpers import cmd, create_request, error_code, png, to_in_progress, upload


async def test_org_b_cannot_reach_org_a_resources(world: World) -> None:
    a, b = world.a, world.b
    req = await create_request(world, a)
    rid = req["id"]
    up = await upload(world, a.requester, rid, "INTAKE")
    file_id = up.json()["id"]
    note = await world.post(
        a.requester, f"/requests/{rid}/notes", {"body": "hello", "client_command_id": cmd()}
    )
    assert note.status_code == 201

    # Org B's staff, with a valid org-B membership, probe org A's ids.
    for member in (b.admin, b.dispatcher, b.requester):
        assert (await world.get(member, f"/requests/{rid}")).status_code == 404
        assert (await world.get(member, f"/requests/{rid}/notes")).status_code == 404
        assert (await world.get(member, f"/requests/{rid}/activity")).status_code == 404
        assert (await world.get(member, f"/files/{file_id}/content")).status_code == 404
    assert (await world.get(b.admin, f"/assets/{a.asset_id}")).status_code == 404
    assert (await world.post(b.dispatcher, f"/requests/{rid}/triage")).status_code == 404
    listing = await world.ok(b.admin, "GET", "/requests")
    assert listing["total"] == 0
    inventory = await world.ok(b.admin, "GET", "/inventory")
    assert all(i["id"] != str(a.item_id) for i in inventory["items"])
    assert (
        await world.post(
            b.admin, f"/inventory/{a.item_id}/stock-additions", {"quantity": 5, "reason": "probe"}
        )
    ).status_code == 404

    # Org B's token cannot select org A at all.
    forged = {**b.admin.headers, "X-Organization-ID": str(a.id)}
    for path in ("/requests", "/reports/dashboard", "/audit", "/notifications", "/stream"):
        response = await world.client.get(f"/api/v1{path}", headers=forged)
        assert response.status_code == 403, path
        assert error_code(response) == "NOT_A_MEMBER"

    # Cross-org references in a create body are rejected, not silently accepted.
    body = {
        "title": "Cross tenant attempt",
        "description": "Trying to use org A's property and category from org B.",
        "category_id": str(a.category_id),
        "property_id": str(a.property_id),
    }
    assert (await world.post(b.requester, "/requests", body)).status_code == 422


async def test_notifications_are_private_to_their_recipient(world: World) -> None:
    a = world.a
    await to_in_progress(world, a)
    mine = await world.ok(a.tech, "GET", "/notifications")
    assert mine["total"] >= 1 and mine["unread_count"] >= 1
    nid = mine["items"][0]["id"]
    # Same organization, different user: cannot read or mark it.
    assert (await world.post(a.tech2, f"/notifications/{nid}/read")).status_code == 404
    assert (await world.post(a.admin, f"/notifications/{nid}/read")).status_code == 404
    other = await world.ok(a.tech2, "GET", "/notifications")
    assert nid not in [n["id"] for n in other["items"]]
    after = await world.ok(a.tech, "POST", f"/notifications/{nid}/read", json={})
    assert after["unread_count"] == mine["unread_count"] - 1


async def test_deactivated_member_loses_access_immediately(world: World) -> None:
    a = world.a
    assert (await world.get(a.requester2, "/requests")).status_code == 200
    await world.ok(
        a.admin, "PATCH", f"/staff/{a.requester2.membership_id}", json={"is_active": False}
    )
    denied = await world.get(a.requester2, "/requests")
    assert denied.status_code == 403 and error_code(denied) == "MEMBERSHIP_DEACTIVATED"
    # Admins cannot deactivate or re-role themselves.
    own = await world.call(
        a.admin, "PATCH", f"/staff/{a.admin.membership_id}", json={"role": "TECHNICIAN"}
    )
    assert own.status_code == 403


async def test_missing_and_bad_credentials(world: World) -> None:
    assert (await world.client.get("/api/v1/requests")).status_code == 401
    bad = await world.client.get(
        "/api/v1/requests",
        headers={"Authorization": "Bearer nope", "X-Organization-ID": str(world.a.id)},
    )
    assert bad.status_code == 401
    login = await world.client.post(
        "/api/v1/auth/login", json={"email": "admin@a.example.com", "password": "wrong"}
    )
    assert login.status_code == 401 and error_code(login) == "INVALID_CREDENTIALS"


async def test_login_rate_limit_and_logout_revokes(world: World) -> None:
    for _ in range(settings.LOGIN_MAX_FAILURES):
        r = await world.client.post(
            "/api/v1/auth/login", json={"email": "tech@b.example.com", "password": "bad"}
        )
        assert r.status_code == 401
    limited = await world.client.post(
        "/api/v1/auth/login", json={"email": "tech@b.example.com", "password": "Test-Password-123"}
    )
    assert limited.status_code == 429
    ok = await world.client.post(
        "/api/v1/auth/login", json={"email": "admin@b.example.com", "password": "Test-Password-123"}
    )
    assert ok.status_code == 200
    token = ok.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": str(world.b.id)}
    assert (await world.client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (await world.client.post("/api/v1/auth/logout", headers=headers)).status_code == 200
    revoked = await world.client.get("/api/v1/auth/me", headers=headers)
    assert revoked.status_code == 401 and error_code(revoked) == "SESSION_REVOKED"


async def test_file_upload_validation_and_protected_download(world: World) -> None:
    a = world.a
    req = await create_request(world, a)
    rid = req["id"]
    good = await upload(world, a.requester, rid, "INTAKE", data=png((1, 2, 3)))
    assert good.status_code == 201
    file_id = good.json()["id"]

    fake = await upload(world, a.requester, rid, "INTAKE", data=b"GIF89a not really an image")
    assert fake.status_code == 422 and error_code(fake) == "FILE_TYPE_UNSUPPORTED"
    empty = await upload(world, a.requester, rid, "INTAKE", data=b"")
    assert empty.status_code == 422
    huge = await upload(
        world, a.requester, rid, "INTAKE", data=png() + b"\0" * (settings.MAX_UPLOAD_BYTES + 10)
    )
    assert huge.status_code == 413

    # Failed uploads left nothing behind.
    files = await world.ok(a.requester, "GET", f"/requests/{rid}/files")
    assert len(files) == 1

    # Intake limit is 3.
    for _ in range(2):
        assert (await upload(world, a.requester, rid, "INTAKE")).status_code == 201
    fourth = await upload(world, a.requester, rid, "INTAKE")
    assert fourth.status_code == 409 and error_code(fourth) == "INTAKE_IMAGE_LIMIT"

    # Authorized users download; others cannot, and anonymous cannot.
    ok = await world.get(a.dispatcher, f"/files/{file_id}/content")
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png"
    assert (await world.get(a.requester2, f"/files/{file_id}/content")).status_code == 404
    assert (await world.get(a.tech, f"/files/{file_id}/content")).status_code == 404
    assert (await world.client.get(f"/api/v1/files/{file_id}/content")).status_code == 401


async def test_upload_replay_creates_one_record(world: World) -> None:
    a = world.a
    req = await create_request(world, a)
    command = cmd()
    first = await upload(world, a.requester, req["id"], "INTAKE", command=command)
    second = await upload(world, a.requester, req["id"], "INTAKE", command=command)
    assert first.status_code == 201 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(await world.ok(a.requester, "GET", f"/requests/{req['id']}/files")) == 1
    different = await upload(
        world, a.requester, req["id"], "INTAKE", command=command, data=png((9, 9, 9))
    )
    assert different.status_code == 409 and error_code(different) == "COMMAND_ID_REUSED"
