import pytest
from httpx import AsyncClient

from app.models.models import MemberRole


@pytest.mark.asyncio
async def test_organization_data_isolation(client: AsyncClient, setup_test_data, auth_headers):
    data = setup_test_data

    # Org 1 owner
    org1_headers = auth_headers(data["owner"], data["org1"], MemberRole.OWNER)
    # Org 2 headers (using same owner user or client who is not a member of Org 2 or with org2 id)
    org2_headers = auth_headers(data["owner"], data["org2"], MemberRole.VIEWER)

    # 1. Create a request in Org 1
    create_resp = await client.post(
        "/api/v1/requests",
        json={"title": "Confidential Repair Org 1"},
        headers=org1_headers,
    )
    assert create_resp.status_code == 201
    sr_id = create_resp.json()["id"]

    # 2. Org 1 can see the request
    list_org1 = await client.get("/api/v1/requests", headers=org1_headers)
    assert list_org1.status_code == 200
    ids_org1 = [item["id"] for item in list_org1.json()["items"]]
    assert sr_id in ids_org1

    # 3. Org 2 listing CANNOT see Org 1 requests
    list_org2 = await client.get("/api/v1/requests", headers=org2_headers)
    assert list_org2.status_code == 200
    ids_org2 = [item["id"] for item in list_org2.json()["items"]]
    assert sr_id not in ids_org2

    # 4. Org 2 directly accessing Org 1 request returns 404 Not Found
    get_org2 = await client.get(f"/api/v1/requests/{sr_id}", headers=org2_headers)
    assert get_org2.status_code == 404

    # 5. Org 2 cannot transition status of Org 1 request
    trans_org2 = await client.post(
        f"/api/v1/requests/{sr_id}/status",
        json={"status": "triaged"},
        headers=org2_headers,
    )
    assert trans_org2.status_code == 404
