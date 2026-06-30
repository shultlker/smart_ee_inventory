import pytest
from fastapi.testclient import TestClient


def test_list_slots(client: TestClient) -> None:
    resp = client.get("/api/v1/slots")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert "slot_code" in data[0]
        assert "cabinet_code" in data[0]


def test_list_slots_by_cabinet(client: TestClient) -> None:
    bins_resp = client.get("/api/v1/bins")
    assert bins_resp.status_code == 200
    bins = bins_resp.json()
    if not bins:
        pytest.skip("no bins in database")
    resp = client.get("/api/v1/slots", params={"cabinet_id": bins[0]["id"]})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_inventory(client: TestClient) -> None:
    resp = client.get("/api/v1/inventory")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        row = data[0]
        assert "part_number" in row
        assert "slot_code" in row
        assert "quantity" in row
        assert "available_qty" in row


def test_list_inventory_low_stock(client: TestClient) -> None:
    resp = client.get("/api/v1/inventory", params={"low_stock_only": True})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
