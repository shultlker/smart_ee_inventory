from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DEMO_CSV = Path(__file__).resolve().parents[2] / "scripts" / "demo_bom.csv"


def _seeded(client: TestClient) -> bool:
    bins = client.get("/api/v1/bins").json()
    parts = client.get("/api/v1/components").json()
    return bool(bins and parts)


def test_preview_bom_api(client: TestClient) -> None:
    if not _seeded(client):
        pytest.skip("need seed data")
    text = _DEMO_CSV.read_text(encoding="utf-8")
    resp = client.post("/api/v1/boms/preview", json={"csv_text": text, "kit_qty": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bom_code"] == "DEMO-BOM-001"
    assert body["summary"]["ok"] == 3
    assert len(body["highlight_slot_ids"]) == 3


def test_import_and_analyze_bom_api(client: TestClient) -> None:
    if not _seeded(client):
        pytest.skip("need seed data")
    text = _DEMO_CSV.read_text(encoding="utf-8")
    imp = client.post("/api/v1/boms/import", json={"csv_text": text})
    assert imp.status_code == 201, imp.text
    bom_id = imp.json()["id"]

    listed = client.get("/api/v1/boms")
    assert listed.status_code == 200
    assert any(b["id"] == bom_id for b in listed.json())

    detail = client.get(f"/api/v1/boms/{bom_id}")
    assert detail.status_code == 200
    assert len(detail.json()["lines"]) == 3

    analysis = client.get(f"/api/v1/boms/{bom_id}/analysis", params={"kit_qty": 1})
    assert analysis.status_code == 200
    assert analysis.json()["lines"][0]["slots"]


def test_import_unknown_part_rejected(client: TestClient) -> None:
    text = """bom_code,bom_name,version
BAD-001,坏数据,1.0
part_number,quantity
NO-SUCH-PART,1
"""
    resp = client.post("/api/v1/boms/import", json={"csv_text": text})
    assert resp.status_code == 422
