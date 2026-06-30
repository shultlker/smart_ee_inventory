import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import BinCabinet, BinSlot, InventoryItem, Part
from backend.schemas.inventory_edit import InventoryItemUpdate
from backend.services.inventory_edit_service import update_inventory_item
from shared.constants import OperationStatus, SlotStatus


@pytest.mark.asyncio
async def test_manual_edit_inventory_item(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-EDIT", name="Edit", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="E-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.OCCUPIED,
        rfid_tag_epc="EPC-EDIT-1",
    )
    part = Part(part_number="P-EDIT", name="Edit Part")
    db_session.add_all([slot, part])
    await db_session.flush()
    inv = InventoryItem(part_id=part.id, slot_id=slot.id, quantity=10, min_stock=2)
    db_session.add(inv)
    await db_session.commit()

    op = await update_inventory_item(
        db_session,
        inv.id,
        InventoryItemUpdate(quantity=15, min_stock=3, note="盘点调整"),
    )
    assert op["operation"] == "manual_edit"
    assert op["status"] == OperationStatus.CONFIRMED
    assert op["quantity_before"] == 10
    assert op["quantity_after"] == 15

    await db_session.refresh(inv)
    assert inv.quantity == 15
    assert inv.min_stock == 3
