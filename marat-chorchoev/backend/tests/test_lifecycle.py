import pytest
from httpx import AsyncClient

from app.models.models import MemberRole


@pytest.mark.asyncio
async def test_full_request_lifecycle(client: AsyncClient, setup_test_data, auth_headers):
    data = setup_test_data
    owner_headers = auth_headers(data["owner"], data["org1"], MemberRole.OWNER)
    tech_headers = auth_headers(data["tech"], data["org1"], MemberRole.TECHNICIAN)

    # 1. Create Service Request
    create_payload = {
        "title": "Air Conditioner Leaking",
        "description": "Floor 2 unit is leaking condensate water",
        "property_id": str(data["property"].id),
        "asset_id": str(data["asset"].id),
        "category_id": str(data["category"].id),
        "priority": "high",
    }
    resp = await client.post("/api/v1/requests", json=create_payload, headers=owner_headers)
    assert resp.status_code == 201
    sr_data = resp.json()
    sr_id = sr_data["id"]
    assert sr_data["status"] == "submitted"
    assert sr_data["priority"] == "high"
    assert sr_data["request_number"].startswith("REQ-")

    # 2. Triage Request
    resp = await client.post(
        f"/api/v1/requests/{sr_id}/status",
        json={"status": "triaged", "notes": "Triaged by dispatcher"},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "triaged"

    # 3. Assign Technician
    assign_payload = {
        "service_request_id": sr_id,
        "technician_id": str(data["m_tech"].id),
        "notes": "Please check the drip pan",
    }
    resp = await client.post("/api/v1/assignments", json=assign_payload, headers=owner_headers)
    assert resp.status_code == 201
    assign_id = resp.json()["id"]

    # Request status automatically transitions to assigned
    resp = await client.get(f"/api/v1/requests/{sr_id}", headers=owner_headers)
    assert resp.json()["status"] == "assigned"

    # 4. Technician Accepts and Goes On-Site
    resp = await client.post(
        f"/api/v1/assignments/{assign_id}/status",
        json={"status": "accepted"},
        headers=tech_headers,
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/api/v1/assignments/{assign_id}/status",
        json={"status": "on_site"},
        headers=tech_headers,
    )
    assert resp.status_code == 200

    # Service Request should now be in_progress
    resp = await client.get(f"/api/v1/requests/{sr_id}", headers=owner_headers)
    assert resp.json()["status"] == "in_progress"

    # 5. Technician Adds Work Note
    note_resp = await client.post(
        "/api/v1/notes",
        json={"service_request_id": sr_id, "content": "Cleaned drain pipe and replaced seal."},
        headers=tech_headers,
    )
    assert note_resp.status_code == 201

    # 6. Complete Job
    resp = await client.post(
        f"/api/v1/requests/{sr_id}/status",
        json={"status": "completed", "notes": "Leak fixed, tested operational."},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    # 7. Close Request
    resp = await client.post(
        f"/api/v1/requests/{sr_id}/status",
        json={"status": "closed"},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"
