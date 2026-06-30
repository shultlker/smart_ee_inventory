import pytest
from fastapi.testclient import TestClient


def test_health_docs(client: TestClient) -> None:
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_list_bins(client: TestClient) -> None:
    resp = client.get("/api/v1/bins")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert "code" in data[0]
