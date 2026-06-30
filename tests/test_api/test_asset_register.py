import uuid

import pytest
from fastapi.testclient import TestClient


def test_list_assets(client: TestClient) -> None:
    resp = client.get("/api/v1/assets")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_register_asset(client: TestClient) -> None:
    epc = f"E28068940000ASSET{uuid.uuid4().hex[:8].upper()}"
    payload = {
        "bind_type": "asset",
        "rfid_tag_epc": epc,
        "name": "测试万用表",
        "category": "tool",
        "location": "实验室",
    }
    resp = client.post("/api/v1/inventory/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["bind_type"] == "asset"
    assert data["asset"]["name"] == "测试万用表"
    assert data["asset"]["rfid_tag_epc"] == epc.upper()
    assert data["asset"]["status"] == "in_stock"

    assets = client.get("/api/v1/assets").json()
    assert any(a["rfid_tag_epc"] == epc.upper() for a in assets)

    dup = client.post("/api/v1/inventory/register", json=payload)
    assert dup.status_code == 409


def test_register_asset_duplicate_epc_with_slot(client: TestClient) -> None:
    bins_resp = client.get("/api/v1/bins")
    parts_resp = client.get("/api/v1/components")
    bins = bins_resp.json()
    parts = parts_resp.json()
    if not bins or not parts:
        pytest.skip("need seed data")

    epc = f"E28068940000DUPAS{uuid.uuid4().hex[:6].upper()}"
    slot_payload = {
        "bind_type": "slot_material",
        "part_id": parts[0]["id"],
        "cabinet_id": bins[0]["id"],
        "rfid_tag_epc": epc,
        "quantity": 1,
        "row_no": 8,
        "col_no": 8,
    }
    r1 = client.post("/api/v1/inventory/register", json=slot_payload)
    if r1.status_code == 409 and "已有库存" in r1.text:
        pytest.skip("slot already used")
    assert r1.status_code == 201

    asset_payload = {
        "bind_type": "asset",
        "rfid_tag_epc": epc,
        "name": "冲突测试物件",
    }
    r2 = client.post("/api/v1/inventory/register", json=asset_payload)
    assert r2.status_code == 409
    assert "EPC" in r2.json()["detail"]


def test_asset_manual_take_out_and_return(client: TestClient) -> None:
    epc = f"E28068940000OPS{uuid.uuid4().hex[:8].upper()}"
    reg = client.post(
        "/api/v1/inventory/register",
        json={
            "bind_type": "asset",
            "rfid_tag_epc": epc,
            "name": "手动借还测试",
        },
    )
    assert reg.status_code == 201, reg.text

    out = client.post(
        "/api/v1/assets/take-out",
        json={
            "rfid_tag_epc": epc,
            "user_name": "测试员",
            "project_name": "Demo",
        },
    )
    assert out.status_code == 201, out.text
    out_data = out.json()
    assert out_data["operation"] == "take_out"
    assert out_data["entity_type"] == "asset"
    assert out_data["status"] == "confirmed"
    assert out_data["quantity_after"] == 0

    dup_out = client.post(
        "/api/v1/assets/take-out",
        json={
            "rfid_tag_epc": epc,
            "user_name": "测试员",
            "project_name": "Demo",
        },
    )
    assert dup_out.status_code == 409

    ret = client.post(
        "/api/v1/assets/return",
        json={"rfid_tag_epc": epc, "note": "归还"},
    )
    assert ret.status_code == 201, ret.text
    ret_data = ret.json()
    assert ret_data["operation"] == "return"
    assert ret_data["quantity_after"] == 1

    assets = client.get("/api/v1/assets").json()
    asset = next(a for a in assets if a["rfid_tag_epc"] == epc.upper())
    assert asset["status"] == "in_stock"

