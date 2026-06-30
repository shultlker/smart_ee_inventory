import uuid

import pytest
from fastapi.testclient import TestClient


def test_register_inventory(client: TestClient) -> None:
    bins_resp = client.get("/api/v1/bins")
    parts_resp = client.get("/api/v1/components")
    assert bins_resp.status_code == 200
    assert parts_resp.status_code == 200
    bins = bins_resp.json()
    parts = parts_resp.json()
    if not bins or not parts:
        pytest.skip("need seed data")

    epc = f"E280689400005022{uuid.uuid4().hex[:8].upper()}"
    payload = {
        "bind_type": "slot_material",
        "part_id": parts[0]["id"],
        "cabinet_id": bins[0]["id"],
        "rfid_tag_epc": epc,
        "quantity": 42,
        "min_stock": 5,
        "row_no": 9,
        "col_no": 9,
        "layer_no": 1,
    }
    resp = client.post("/api/v1/inventory/register", json=payload)
    if resp.status_code == 409 and "已有库存" in resp.text:
        pytest.skip("target slot already has inventory from prior run")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["slot_item"]["part_id"] == parts[0]["id"]
    assert data["slot_item"]["quantity"] == 42
    assert data["slot_item"]["rfid_tag_epc"] == epc.upper()
    assert data["slot_item"]["slot_code"]

    dup = client.post("/api/v1/inventory/register", json=payload)
    assert dup.status_code == 409


def test_register_inventory_duplicate_epc(client: TestClient) -> None:
    bins_resp = client.get("/api/v1/bins")
    parts_resp = client.get("/api/v1/components")
    bins = bins_resp.json()
    parts = parts_resp.json()
    if len(parts) < 2 or not bins:
        pytest.skip("need seed data")

    epc = "E28068940000502244813DUP1"
    first = {
        "bind_type": "slot_material",
        "part_id": parts[0]["id"],
        "cabinet_id": bins[0]["id"],
        "rfid_tag_epc": epc,
        "quantity": 1,
        "row_no": 4,
        "col_no": 4,
    }
    r1 = client.post("/api/v1/inventory/register", json=first)
    if r1.status_code == 409 and "已有库存" in r1.text:
        pytest.skip("slot already used in prior test run")

    assert r1.status_code == 201

    second = {
        "bind_type": "slot_material",
        "part_id": parts[1]["id"],
        "cabinet_id": bins[0]["id"],
        "rfid_tag_epc": epc,
        "quantity": 1,
        "row_no": 4,
        "col_no": 5,
    }
    r2 = client.post("/api/v1/inventory/register", json=second)
    assert r2.status_code == 409
    assert "EPC" in r2.json()["detail"]
