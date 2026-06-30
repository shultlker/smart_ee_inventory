import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import BinCabinet, BinSlot, InventoryItem, Part
from backend.schemas.operation import OperationConfirmRequest, ReturnConfirm, TakeOutConfirm
from backend.services.operation_service import (
    cancel_inventory_operation,
    confirm_inventory_operation,
    create_presence_pending_action,
)
from shared.constants import BinStatus, OperationStatus, SlotStatus


@pytest.mark.asyncio
async def test_pending_take_out_and_confirm(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-T1", name="Test", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="T1-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.OCCUPIED,
        rfid_tag_epc="EPC-PENDING-OUT",
    )
    part = Part(part_number="P-1", name="Part 1")
    db_session.add_all([slot, part])
    await db_session.flush()
    inv = InventoryItem(part_id=part.id, slot_id=slot.id, quantity=10, status="in_stock")
    db_session.add(inv)
    await db_session.commit()

    pending = await create_presence_pending_action(db_session, "EPC-PENDING-OUT", "disappear")
    assert pending is not None
    assert pending["status"] == OperationStatus.PENDING
    assert pending["operation"] == "take_out"

    await db_session.refresh(slot)
    assert slot.status == SlotStatus.PENDING_CHECKOUT
    await db_session.refresh(cabinet)
    assert cabinet.status == BinStatus.CHECKOUT_UNREGISTERED

    confirmed = await confirm_inventory_operation(
        db_session,
        pending["id"],
        OperationConfirmRequest(
            take_out=TakeOutConfirm(user_name="张三", project_name="Demo"),
        ),
    )
    assert confirmed["status"] == OperationStatus.CONFIRMED
    assert confirmed["quantity_after"] == 9
    assert confirmed["user_name"] == "张三"

    await db_session.refresh(inv)
    await db_session.refresh(slot)
    assert inv.quantity == 9
    assert slot.status == SlotStatus.CHECKED_OUT
    await db_session.refresh(cabinet)
    assert cabinet.status == BinStatus.CHECKED_OUT


@pytest.mark.asyncio
async def test_pending_return_with_consumption(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-T2", name="Test2", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="T2-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.CHECKED_OUT,
        rfid_tag_epc="EPC-PENDING-IN",
    )
    part = Part(part_number="P-2", name="Part 2")
    db_session.add_all([slot, part])
    await db_session.flush()
    inv = InventoryItem(part_id=part.id, slot_id=slot.id, quantity=8, status="in_stock")
    db_session.add(inv)
    await db_session.commit()

    pending = await create_presence_pending_action(db_session, "EPC-PENDING-IN", "appear")
    assert pending is not None
    assert pending["operation"] == "return"

    await db_session.refresh(slot)
    assert slot.status == SlotStatus.PENDING_RETURN

    confirmed = await confirm_inventory_operation(
        db_session,
        pending["id"],
        OperationConfirmRequest(return_info=ReturnConfirm(consumed_qty=3)),
    )
    assert confirmed["quantity_after"] == 6  # 8 + 1 - 3
    assert confirmed["consumed_qty"] == 3

    await db_session.refresh(slot)
    assert slot.status == SlotStatus.OCCUPIED
    await db_session.refresh(cabinet)
    assert cabinet.status == BinStatus.ACTIVE


@pytest.mark.asyncio
async def test_cancel_pending_take_out(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-T3", name="T3", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="T3-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.OCCUPIED,
        rfid_tag_epc="EPC-CANCEL",
    )
    part = Part(part_number="P-3", name="P3")
    db_session.add_all([slot, part])
    await db_session.flush()
    db_session.add(InventoryItem(part_id=part.id, slot_id=slot.id, quantity=5))
    await db_session.commit()

    pending = await create_presence_pending_action(db_session, "EPC-CANCEL", "disappear")
    assert pending is not None
    cancelled = await cancel_inventory_operation(db_session, pending["id"])
    assert cancelled["status"] == OperationStatus.CANCELLED
    await db_session.refresh(slot)
    assert slot.status == SlotStatus.CHECKOUT_UNREGISTERED
    await db_session.refresh(cabinet)
    assert cabinet.status == BinStatus.CHECKOUT_UNREGISTERED


@pytest.mark.asyncio
async def test_cancel_pending_return(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-T4", name="T4", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="T4-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.CHECKED_OUT,
        rfid_tag_epc="EPC-CANCEL-IN",
    )
    part = Part(part_number="P-4", name="P4")
    db_session.add_all([slot, part])
    await db_session.flush()
    db_session.add(InventoryItem(part_id=part.id, slot_id=slot.id, quantity=8))
    await db_session.commit()

    pending = await create_presence_pending_action(db_session, "EPC-CANCEL-IN", "appear")
    assert pending is not None
    cancelled = await cancel_inventory_operation(db_session, pending["id"])
    assert cancelled["status"] == OperationStatus.CANCELLED
    await db_session.refresh(slot)
    assert slot.status == SlotStatus.RETURN_UNREGISTERED
    await db_session.refresh(cabinet)
    assert cabinet.status == BinStatus.RETURN_UNREGISTERED


@pytest.mark.asyncio
async def test_checkout_unregistered_reconcile_on_return(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-T5", name="T5", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="T5-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.CHECKOUT_UNREGISTERED,
        rfid_tag_epc="EPC-RECON",
    )
    part = Part(part_number="P-5", name="P5")
    db_session.add_all([slot, part])
    await db_session.flush()
    inv = InventoryItem(part_id=part.id, slot_id=slot.id, quantity=10)
    db_session.add(inv)
    await db_session.commit()

    pending = await create_presence_pending_action(db_session, "EPC-RECON", "appear")
    assert pending is not None
    assert "from_checkout_unregistered" in (pending.get("note") or "")

    confirmed = await confirm_inventory_operation(
        db_session,
        pending["id"],
        OperationConfirmRequest(return_info=ReturnConfirm(consumed_qty=0)),
    )
    assert confirmed["quantity_after"] == 10

    await db_session.refresh(slot)
    assert slot.status == SlotStatus.OCCUPIED
    await db_session.refresh(inv)
    assert inv.quantity == 10
