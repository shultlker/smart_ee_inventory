import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset, BinCabinet, BinSlot, InventoryItem, Part
from backend.services.inventory_manage_service import (
    bind_tag,
    delete_inventory_record,
    rebind_tag,
    unbind_tag,
)
from shared.constants import SlotStatus


@pytest.mark.asyncio
async def test_slot_tag_bind_rebind_unbind_delete(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-TG", name="Tag", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="TG-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.OCCUPIED,
    )
    part = Part(part_number="P-TG", name="Tag Part")
    db_session.add_all([slot, part])
    await db_session.flush()
    item = InventoryItem(part_id=part.id, slot_id=slot.id, quantity=5, status="in_stock")
    db_session.add(item)
    await db_session.commit()

    epc1 = f"EPC-BIND{uuid.uuid4().hex[:8].upper()}"
    epc2 = f"EPC-REBIND{uuid.uuid4().hex[:8].upper()}"

    await bind_tag(
        db_session,
        entity_type="slot_material",
        record_id=item.id,
        rfid_tag_epc=epc1,
    )
    await db_session.refresh(slot)
    assert slot.rfid_tag_epc == epc1

    with pytest.raises(ValueError, match="已绑定"):
        await bind_tag(
            db_session,
            entity_type="slot_material",
            record_id=item.id,
            rfid_tag_epc=epc2,
        )

    await rebind_tag(
        db_session,
        entity_type="slot_material",
        record_id=item.id,
        rfid_tag_epc=epc2,
    )
    await db_session.refresh(slot)
    assert slot.rfid_tag_epc == epc2

    await unbind_tag(db_session, entity_type="slot_material", record_id=item.id)
    await db_session.refresh(slot)
    assert slot.rfid_tag_epc is None

    await bind_tag(
        db_session,
        entity_type="slot_material",
        record_id=item.id,
        rfid_tag_epc=epc1,
    )
    await delete_inventory_record(
        db_session,
        entity_type="slot_material",
        record_id=item.id,
    )
    await db_session.refresh(slot)
    assert slot.rfid_tag_epc is None
    assert slot.status == SlotStatus.EMPTY
    assert await db_session.get(InventoryItem, item.id) is None


@pytest.mark.asyncio
async def test_asset_tag_lifecycle(db_session: AsyncSession) -> None:
    asset = Asset(
        asset_code="AST-TG",
        name="Tag Asset",
        status="in_stock",
    )
    db_session.add(asset)
    await db_session.commit()

    epc = f"EPC-AST{uuid.uuid4().hex[:8].upper()}"
    await bind_tag(
        db_session,
        entity_type="asset",
        record_id=asset.id,
        rfid_tag_epc=epc,
    )
    await db_session.refresh(asset)
    assert asset.rfid_tag_epc == epc

    await unbind_tag(db_session, entity_type="asset", record_id=asset.id)
    await db_session.refresh(asset)
    assert asset.rfid_tag_epc is None

    await delete_inventory_record(
        db_session,
        entity_type="asset",
        record_id=asset.id,
    )
    assert await db_session.get(Asset, asset.id) is None


def test_inventory_manage_api(client: TestClient) -> None:
    inv = client.get("/api/v1/inventory").json()
    if not inv:
        pytest.skip("no inventory items")

    item = inv[0]
    item_id = item["id"]
    epc = f"E28068940000MGT{uuid.uuid4().hex[:6].upper()}"

    if item.get("rfid_tag_epc"):
        r = client.post(
            "/api/v1/inventory/manage/unbind-tag",
            json={"entity_type": "slot_material", "record_id": item_id},
        )
        assert r.status_code == 201, r.text

    r_bind = client.post(
        "/api/v1/inventory/manage/bind-tag",
        json={
            "entity_type": "slot_material",
            "record_id": item_id,
            "rfid_tag_epc": epc,
        },
    )
    assert r_bind.status_code == 201, r_bind.text
    assert r_bind.json()["operation"] == "tag_bind"

    epc2 = f"E28068940000MG2{uuid.uuid4().hex[:6].upper()}"
    r_rebind = client.post(
        "/api/v1/inventory/manage/rebind-tag",
        json={
            "entity_type": "slot_material",
            "record_id": item_id,
            "rfid_tag_epc": epc2,
        },
    )
    assert r_rebind.status_code == 201, r_rebind.text

    r_unbind = client.post(
        "/api/v1/inventory/manage/unbind-tag",
        json={"entity_type": "slot_material", "record_id": item_id},
    )
    assert r_unbind.status_code == 201, r_unbind.text

    inv_after = client.get("/api/v1/inventory").json()
    row = next(i for i in inv_after if i["id"] == item_id)
    assert row.get("rfid_tag_epc") is None
