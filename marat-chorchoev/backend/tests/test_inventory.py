import uuid

import pytest
from httpx import AsyncClient

from app.models.models import MemberRole


@pytest.mark.asyncio
async def test_inventory_consumption_and_idempotency(client: AsyncClient, setup_test_data, auth_headers):
    data = setup_test_data
    owner_headers = auth_headers(data["owner"], data["org1"], MemberRole.OWNER)

    # 1. Create a service request
    r = await client.post("/api/v1/requests", json={"title": "Filter Replacement"}, headers=owner_headers)
    sr_id = r.json()["id"]

    item_id = str(data["item"].id)
    cmd_id = f"cmd-{uuid.uuid4()}"

    # 2. Consume 5 items with idempotency key
    consume_payload = {
        "service_request_id": sr_id,
        "quantity": 5.0,
        "client_command_id": cmd_id,
        "notes": "Installed 5 filters on unit 1",
    }
    resp1 = await client.post(f"/api/v1/inventory/{item_id}/consume", json=consume_payload, headers=owner_headers)
    assert resp1.status_code == 200
    res_data1 = resp1.json()
    assert res_data1["status"] == "consumed"
    assert res_data1["quantity"] == 5.0

    # 3. Duplicate request with identical client_command_id returns already_processed without double-deduction
    resp2 = await client.post(f"/api/v1/inventory/{item_id}/consume", json=consume_payload, headers=owner_headers)
    assert resp2.status_code == 200
    res_data2 = resp2.json()
    assert res_data2["status"] == "already_processed"
    assert res_data2["id"] == res_data1["id"]

    # 4. Check inventory stock is 95 (100 - 5)
    inv_list = await client.get("/api/v1/inventory", headers=owner_headers)
    assert inv_list.status_code == 200
    items = inv_list.json()["items"]
    target = next(i for i in items if i["id"] == item_id)
    assert target["stock_quantity"] == 95.0

    # 5. Over-consumption failure
    excess_payload = {
        "service_request_id": sr_id,
        "quantity": 1000.0,
    }
    excess_resp = await client.post(f"/api/v1/inventory/{item_id}/consume", json=excess_payload, headers=owner_headers)
    assert excess_resp.status_code == 400
    assert "insufficient" in excess_resp.json()["detail"].lower()
