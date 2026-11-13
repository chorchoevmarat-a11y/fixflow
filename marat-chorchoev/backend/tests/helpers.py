"""Small builders shared by the API tests."""

import io
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from PIL import Image

from tests.conftest import Member, OrgFixture, World

TZ = ZoneInfo("Asia/Bishkek")


def cmd() -> str:
    """A fresh client command id."""
    return f"cmd-{uuid.uuid4().hex}"


def slot(
    weeks_ahead: int = 1, weekday: int = 0, hour: int = 10, minutes: int = 120
) -> dict[str, str]:
    """A future appointment inside Mon-Fri 09:00-18:00 Bishkek time."""
    today = datetime.now(TZ).date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=weeks_ahead)
    start = datetime.combine(monday + timedelta(days=weekday), time(hour), TZ).astimezone(UTC)
    return {
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(minutes=minutes)).isoformat(),
    }


def png(color: tuple[int, int, int] = (30, 120, 90), size: tuple[int, int] = (64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def request_body(org: OrgFixture, **overrides) -> dict:
    body = {
        "title": "Air handler is making noise",
        "description": "The rooftop unit rattles loudly whenever the fan starts.",
        "category_id": str(org.category_id),
        "property_id": str(org.property_id),
        "asset_id": str(org.asset_id),
        "priority": "HIGH",
    }
    body.update(overrides)
    return body


async def create_request(
    world: World, org: OrgFixture, requester: Member | None = None, **overrides
) -> dict:
    return await world.ok(
        requester or org.requester, "POST", "/requests", json=request_body(org, **overrides)
    )


async def upload(
    world: World,
    member: Member,
    request_id: str,
    kind: str,
    *,
    data: bytes | None = None,
    command: str | None = None,
    **form,
):
    return await world.call(
        member,
        "POST",
        f"/requests/{request_id}/files",
        data={"kind": kind, "client_command_id": command or cmd(), **form},
        files={"file": ("photo.png", data if data is not None else png(), "image/png")},
    )


async def to_triaged(world: World, org: OrgFixture, **overrides) -> dict:
    req = await create_request(world, org, **overrides)
    return await world.ok(org.dispatcher, "POST", f"/requests/{req['id']}/triage", json={})


async def to_scheduled(
    world: World, org: OrgFixture, tech: Member | None = None, when: dict | None = None, **overrides
) -> dict:
    req = await to_triaged(world, org, **overrides)
    body = {"technician_id": str((tech or org.tech).technician_id), **(when or slot())}
    return await world.ok(org.dispatcher, "POST", f"/requests/{req['id']}/assign", json=body)


async def to_accepted(world: World, org: OrgFixture, **kwargs) -> dict:
    req = await to_scheduled(world, org, **kwargs)
    return await world.ok(
        kwargs.get("tech") or org.tech, "POST", f"/requests/{req['id']}/accept", json={}
    )


async def to_in_progress(world: World, org: OrgFixture, **kwargs) -> dict:
    req = await to_accepted(world, org, **kwargs)
    return await world.ok(
        kwargs.get("tech") or org.tech, "POST", f"/requests/{req['id']}/start", json={}
    )


async def to_completed(world: World, org: OrgFixture, **kwargs) -> dict:
    req = await to_in_progress(world, org, **kwargs)
    tech = kwargs.get("tech") or org.tech
    assert (await upload(world, tech, req["id"], "COMPLETION")).status_code == 201
    return await world.ok(
        tech,
        "POST",
        f"/requests/{req['id']}/complete",
        json={"completion_note": "Replaced the worn fan belt and tested the unit."},
    )


def error_code(response) -> str:
    return response.json()["error"]["code"]
