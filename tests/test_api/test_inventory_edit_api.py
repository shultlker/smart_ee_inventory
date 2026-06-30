"""API tests for manual inventory / asset edit."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import create_app
from backend.models import Asset, BinCabinet, BinSlot, InventoryItem, Part
from shared.constants import SlotStatus


@pytest.mark.asyncio
async def test_patch_inventory_item_api(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-API-ED", name="API", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="AE-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.OCCUPIED,
    )
    part = Part(part_number="P-API-ED", name="API Part")
    db_session.add_all([slot, part])
    await db_session.flush()
    inv = InventoryItem(part_id=part.id, slot_id=slot.id, quantity=8, min_stock=2)
    db_session.add(inv)
    await db_session.commit()

    with TestClient(create_app()) as client:
        resp = client.patch(
            f"/api/v1/inventory/items/{inv.id}",
            json={"quantity": 12, "min_stock": 3, "note": "API 调整"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["operation"] == "manual_edit"
    assert body["quantity_before"] == 8
    assert body["quantity_after"] == 12


@pytest.mark.asyncio
async def test_patch_asset_api(db_session: AsyncSession) -> None:
    asset = Asset(
        asset_code="AST-API-ED",
        name="Old Name",
        category="tool",
        rfid_tag_epc="EPC-API-ED-1",
        status="in_stock",
    )
    db_session.add(asset)
    await db_session.commit()

    with TestClient(create_app()) as client:
        resp = client.patch(
            f"/api/v1/assets/{asset.id}",
            json={"name": "New Name", "location": "Shelf A", "note": "rename"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["operation"] == "manual_edit"
    assert body["asset_id"] == asset.id
    assert body.get("asset_name") == "New Name" or body.get("note")
