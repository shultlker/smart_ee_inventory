import uuid

import pytest
from fastapi.testclient import TestClient


def test_list_categories(client: TestClient) -> None:
    resp = client.get("/api/v1/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert "code" in data[0]
        assert "name" in data[0]


def test_create_component(client: TestClient) -> None:
    cats = client.get("/api/v1/categories").json()
    category_id = cats[0]["id"] if cats else None

    payload = {
        "part_number": f"TEST-PART-{uuid.uuid4().hex[:8]}",
        "name": "测试电阻 1kΩ",
        "package": "0603",
        "value": "1kΩ",
        "manufacturer": "TestMfg",
    }
    if category_id is not None:
        payload["category_id"] = category_id

    resp = client.post("/api/v1/components", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["part_number"] == payload["part_number"]
    assert body["name"] == payload["name"]
    if category_id is not None:
        assert body["category_id"] == category_id
        assert body["category_name"] is not None

    dup = client.post("/api/v1/components", json=payload)
    assert dup.status_code == 409


def test_create_component_invalid_category(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/components",
        json={
            "part_number": "TEST-PART-BAD-CAT",
            "name": "无效分类测试",
            "category_id": 999999,
        },
    )
    assert resp.status_code == 400
