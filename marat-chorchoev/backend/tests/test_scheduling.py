from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.models.models import MemberRole


@pytest.mark.asyncio
async def test_scheduling_conflict_detection(client: AsyncClient, setup_test_data, auth_headers):
    data = setup_test_data
    owner_headers = auth_headers(data["owner"], data["org1"], MemberRole.OWNER)

    # Create two service requests
    r1 = await client.post("/api/v1/requests", json={"title": "Job A"}, headers=owner_headers)
    r2 = await client.post("/api/v1/requests", json={"title": "Job B"}, headers=owner_headers)
    sr1_id = r1.json()["id"]
    sr2_id = r2.json()["id"]

    now = datetime.now(timezone.utc)
    slot1_start = now + timedelta(days=1, hours=9)
    slot1_end = now + timedelta(days=1, hours=11)

    # Assign technician to Job A for 9:00 - 11:00
    resp1 = await client.post(
        "/api/v1/assignments",
        json={
            "service_request_id": sr1_id,
            "technician_id": str(data["m_tech"].id),
            "start_at": slot1_start.isoformat(),
            "end_at": slot1_end.isoformat(),
        },
        headers=owner_headers,
    )
    assert resp1.status_code == 201

    # Attempt to assign the same technician to Job B overlapping 10:00 - 12:00
    overlap_start = now + timedelta(days=1, hours=10)
    overlap_end = now + timedelta(days=1, hours=12)

    resp2 = await client.post(
        "/api/v1/assignments",
        json={
            "service_request_id": sr2_id,
            "technician_id": str(data["m_tech"].id),
            "start_at": overlap_start.isoformat(),
            "end_at": overlap_end.isoformat(),
        },
        headers=owner_headers,
    )
    # Conflict detected!
    assert resp2.status_code == 409
    assert "conflict" in resp2.json()["detail"].lower()

    # Non-overlapping assignment for 13:00 - 15:00 should succeed
    slot2_start = now + timedelta(days=1, hours=13)
    slot2_end = now + timedelta(days=1, hours=15)
    resp3 = await client.post(
        "/api/v1/assignments",
        json={
            "service_request_id": sr2_id,
            "technician_id": str(data["m_tech"].id),
            "start_at": slot2_start.isoformat(),
            "end_at": slot2_end.isoformat(),
        },
        headers=owner_headers,
    )
    assert resp3.status_code == 201
