import pytest
from fastapi.testclient import TestClient


def test_list_rfid_events(client: TestClient) -> None:
    resp = client.get("/api/v1/rfid/events")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
