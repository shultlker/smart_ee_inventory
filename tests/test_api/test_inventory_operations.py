import pytest
from fastapi.testclient import TestClient


def test_list_inventory_operations(client: TestClient) -> None:
    resp = client.get("/api/v1/inventory/operations", params={"limit": 10})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_register_creates_operation(client: TestClient) -> None:
    bins_resp = client.get("/api/v1/bins")
    parts_resp = client.get("/api/v1/components")
    bins = bins_resp.json()
    parts = parts_resp.json()
    if not bins or not parts:
        pytest.skip("need seed data")

    epc = "E28068940000502244813WDOG"
    payload = {
        "bind_type": "slot_material",
        "part_id": parts[0]["id"],
        "cabinet_id": bins[0]["id"],
        "rfid_tag_epc": epc,
        "quantity": 3,
        "min_stock": 1,
        "row_no": 2,
        "col_no": 2,
        "layer_no": 1,
    }
    reg = client.post("/api/v1/inventory/register", json=payload)
    if reg.status_code == 409 and "已有库存" in reg.text:
        pytest.skip("slot already used")
    assert reg.status_code == 201, reg.text

    ops_resp = client.get("/api/v1/inventory/operations", params={"limit": 5})
    assert ops_resp.status_code == 200
    ops = ops_resp.json()
    assert any(o.get("operation") == "register_in" and o.get("epc") == epc.upper() for o in ops)
