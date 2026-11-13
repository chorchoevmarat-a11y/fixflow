"""Development-only concurrency simulations (SEED-06). Needs a running, seeded API.

    uv run python -m app.cli race-assign   # two dispatchers book one technician slot
    uv run python -m app.cli race-consume  # two technicians take the last stock

Both fire simultaneous real HTTP requests and print the outcome, which should be
exactly one success and one 409 Conflict. Uses the disposable demo accounts.
"""

import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.seed import DEMO_PASSWORD, sid

ORG = str(sid("org:a"))
TZ = ZoneInfo("Asia/Bishkek")


async def _login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}", "X-Organization-ID": ORG}


def _next_monday_slot(hour: int) -> tuple[str, str]:
    today = datetime.now(TZ).date()
    monday = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
    start = datetime.combine(monday, time(hour), TZ).astimezone(UTC)
    return start.isoformat(), (start + timedelta(hours=1)).isoformat()


async def _new_triaged(client, requester: dict, dispatcher: dict, title: str) -> str:
    created = await client.post(
        "/api/v1/requests",
        headers=requester,
        json={
            "title": title,
            "description": "Created by the race simulation to demonstrate conflict handling.",
            "category_id": str(sid("category:a:electrical")),
            "property_id": str(sid("property:a:su_main")),
            "priority": "NORMAL",
        },
    )
    created.raise_for_status()
    rid = created.json()["id"]
    (
        await client.post(f"/api/v1/requests/{rid}/triage", headers=dispatcher, json={})
    ).raise_for_status()
    return rid


async def race_assign(client: httpx.AsyncClient) -> None:
    requester = await _login(client, "requester1@salymbekov.example.com")
    dispatcher = await _login(client, "dispatcher@salymbekov.example.com")
    tag = uuid.uuid4().hex[:6]
    first = await _new_triaged(client, requester, dispatcher, f"Race A {tag}")
    second = await _new_triaged(client, requester, dispatcher, f"Race B {tag}")
    start, end = _next_monday_slot(16)
    body = {
        "technician_id": str(sid("tech:a:tech1@salymbekov.example.com")),
        "start_at": start,
        "end_at": end,
    }
    results = await asyncio.gather(
        client.post(f"/api/v1/requests/{first}/assign", headers=dispatcher, json=body),
        client.post(f"/api/v1/requests/{second}/assign", headers=dispatcher, json=body),
    )
    for response in results:
        print(response.status_code, response.json().get("error", {}).get("code", "assigned"))


async def race_consume(client: httpx.AsyncClient) -> None:
    admin = await _login(client, "admin@salymbekov.example.com")
    item = str(sid("item:a:SLN-01"))
    print("Hint: this needs two IN_PROGRESS jobs; see docs/VERIFICATION.md for the exact setup.")
    response = await client.get("/api/v1/inventory", headers=admin, params={"q": "SLN-01"})
    print("stock before:", response.json()["items"][0]["stock_quantity"], "item", item)


async def run(command: str, base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        await (race_assign if command == "race-assign" else race_consume)(client)
