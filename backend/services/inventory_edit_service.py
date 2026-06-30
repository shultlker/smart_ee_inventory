"""Manual inventory record edits with operation logging."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset, BinCabinet, BinSlot, InventoryItem, Part
from backend.schemas.inventory_edit import AssetRecordUpdate, InventoryItemUpdate
from backend.services.inventory_manage_service import (
    _assert_no_pending_asset_ops,
    _assert_no_pending_slot_ops,
    _assert_slot_not_pending_status,
    _get_asset,
    _get_slot_material_row,
)
from backend.services.inventory_service import _create_inventory_operation
from shared.constants import InventoryEntityType, OperationStatus, SlotStatus


def _format_changes(changes: list[str]) -> str:
    return "；".join(changes) if changes else "无字段变更"


async def update_inventory_item(
    session: AsyncSession,
    item_id: int,
    data: InventoryItemUpdate,
) -> dict:
    item, slot, part, cabinet = await _get_slot_material_row(session, item_id)
    await _assert_no_pending_slot_ops(session, slot.id)
    _assert_slot_not_pending_status(slot)

    payload = data.model_dump(exclude_unset=True)
    user_note = payload.pop("note", None)
    if not payload:
        raise ValueError("未提供任何修改字段")

    qty_before = item.quantity
    changes: list[str] = []

    if "quantity" in payload:
        new_qty = payload["quantity"]
        if new_qty != item.quantity:
            changes.append(f"数量 {item.quantity}→{new_qty}")
            item.quantity = new_qty
            if new_qty > 0:
                item.status = "in_stock"
                if slot.status == SlotStatus.EMPTY:
                    slot.status = SlotStatus.OCCUPIED
            elif new_qty == 0:
                item.status = "out_of_stock"

    for field in ("min_stock", "max_stock", "reorder_point", "batch_no"):
        if field not in payload:
            continue
        old = getattr(item, field)
        new = payload[field]
        if old != new:
            label = {
                "min_stock": "最低库存",
                "max_stock": "最高库存",
                "reorder_point": "补货点",
                "batch_no": "批次",
            }[field]
            changes.append(f"{label} {old!r}→{new!r}")
            setattr(item, field, new)

    if not changes:
        raise ValueError("数值与当前记录相同，无需保存")

    note = user_note or f"手动修改 · {_format_changes(changes)}"
    op_row = await _create_inventory_operation(
        session,
        operation="manual_edit",
        entity_type=InventoryEntityType.SLOT_MATERIAL,
        epc=slot.rfid_tag_epc,
        part_id=part.id,
        slot_id=slot.id,
        cabinet_id=cabinet.id,
        quantity_before=qty_before,
        quantity_change=item.quantity - qty_before,
        quantity_after=item.quantity,
        slot_status=slot.status,
        source="manage",
        note=note,
        status=OperationStatus.CONFIRMED,
    )
    await session.commit()
    return op_row


async def update_asset_record(
    session: AsyncSession,
    asset_id: int,
    data: AssetRecordUpdate,
) -> dict:
    asset = await _get_asset(session, asset_id)
    await _assert_no_pending_asset_ops(session, asset.id)

    payload = data.model_dump(exclude_unset=True)
    user_note = payload.pop("note", None)
    if not payload:
        raise ValueError("未提供任何修改字段")

    qty_before = 1 if asset.status == "in_stock" else 0
    changes: list[str] = []

    field_labels = {
        "name": "名称",
        "category": "类别",
        "serial_no": "序列号",
        "location": "位置",
        "remark": "备注",
    }
    for field, label in field_labels.items():
        if field not in payload:
            continue
        old = getattr(asset, field)
        new = payload[field]
        if old != new:
            changes.append(f"{label} {old!r}→{new!r}")
            setattr(asset, field, new)

    if not changes:
        raise ValueError("数值与当前记录相同，无需保存")

    note = user_note or f"手动修改 · {_format_changes(changes)}"
    qty_after = 1 if asset.status == "in_stock" else 0
    op_row = await _create_inventory_operation(
        session,
        operation="manual_edit",
        entity_type=InventoryEntityType.ASSET,
        epc=asset.rfid_tag_epc,
        part_id=None,
        slot_id=None,
        cabinet_id=None,
        asset_id=asset.id,
        quantity_before=qty_before,
        quantity_change=qty_after - qty_before,
        quantity_after=qty_after,
        slot_status=asset.status,
        source="manage",
        note=note,
        status=OperationStatus.CONFIRMED,
    )
    await session.commit()
    return op_row


__all__ = ["update_asset_record", "update_inventory_item"]
