"""Bind / rebind / unbind RFID tags and delete inventory records."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset, BinCabinet, BinSlot, InventoryItem, InventoryOperation, Part
from backend.services.epc_binding import check_epc_available
from backend.services.inventory_service import _create_inventory_operation
from backend.services.operation_service import _sync_cabinet_status
from shared.constants import InventoryEntityType, OperationStatus, SLOT_STATUS_LABELS, SlotStatus


async def _get_slot_material_row(
    session: AsyncSession,
    inventory_item_id: int,
) -> tuple[InventoryItem, BinSlot, Part, BinCabinet]:
    item = await session.get(InventoryItem, inventory_item_id)
    if not item:
        raise ValueError("库存记录不存在")
    slot = await session.get(BinSlot, item.slot_id)
    if not slot:
        raise ValueError("格位不存在")
    part = await session.get(Part, item.part_id)
    if not part:
        raise ValueError("物料不存在")
    cabinet = await session.get(BinCabinet, slot.cabinet_id)
    if not cabinet:
        raise ValueError("料盒不存在")
    return item, slot, part, cabinet


async def _get_asset(session: AsyncSession, asset_id: int) -> Asset:
    asset = await session.get(Asset, asset_id)
    if not asset:
        raise ValueError("非标物件不存在")
    return asset


async def _assert_no_pending_slot_ops(session: AsyncSession, slot_id: int) -> None:
    result = await session.execute(
        select(InventoryOperation.id).where(
            InventoryOperation.slot_id == slot_id,
            InventoryOperation.status == OperationStatus.PENDING,
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise ValueError("该格位有待确认操作，请先处理或取消")


async def _assert_no_pending_asset_ops(session: AsyncSession, asset_id: int) -> None:
    result = await session.execute(
        select(InventoryOperation.id).where(
            InventoryOperation.asset_id == asset_id,
            InventoryOperation.status == OperationStatus.PENDING,
        ).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise ValueError("该物件有待确认操作，请先处理或取消")


def _assert_slot_not_pending_status(slot: BinSlot) -> None:
    if slot.status in (
        SlotStatus.PENDING_CHECKOUT,
        SlotStatus.PENDING_RETURN,
        SlotStatus.CHECKOUT_UNREGISTERED,
        SlotStatus.RETURN_UNREGISTERED,
    ):
        label = SLOT_STATUS_LABELS.get(slot.status, slot.status)
        raise ValueError(f"格位状态为 {label}，无法修改标签或删除库存")


def _normalize_epc(epc: str) -> str:
    return epc.strip().upper()


async def bind_tag(
    session: AsyncSession,
    *,
    entity_type: str,
    record_id: int,
    rfid_tag_epc: str,
) -> dict:
    """为尚无 RFID 的现有库存绑定标签。"""
    epc = _normalize_epc(rfid_tag_epc)

    if entity_type == InventoryEntityType.SLOT_MATERIAL:
        item, slot, part, cabinet = await _get_slot_material_row(session, record_id)
        await _assert_no_pending_slot_ops(session, slot.id)
        _assert_slot_not_pending_status(slot)
        if slot.rfid_tag_epc:
            raise ValueError("该格位已绑定标签，请使用换绑")
        await check_epc_available(session, epc, exclude_slot_id=slot.id)
        slot.rfid_tag_epc = epc
        op_row = await _create_inventory_operation(
            session,
            operation="tag_bind",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=epc,
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=item.quantity,
            quantity_change=0,
            quantity_after=item.quantity,
            slot_status=slot.status,
            source="manage",
            note=f"绑定标签 · {slot.slot_code}",
            status=OperationStatus.CONFIRMED,
        )
        await session.commit()
        return op_row

    if entity_type == InventoryEntityType.ASSET:
        asset = await _get_asset(session, record_id)
        await _assert_no_pending_asset_ops(session, asset.id)
        if asset.rfid_tag_epc:
            raise ValueError("该物件已绑定标签，请使用换绑")
        await check_epc_available(session, epc, exclude_asset_id=asset.id)
        asset.rfid_tag_epc = epc
        op_row = await _create_inventory_operation(
            session,
            operation="tag_bind",
            entity_type=InventoryEntityType.ASSET,
            epc=epc,
            part_id=None,
            slot_id=None,
            cabinet_id=None,
            asset_id=asset.id,
            quantity_before=1 if asset.status == "in_stock" else 0,
            quantity_change=0,
            quantity_after=1 if asset.status == "in_stock" else 0,
            slot_status=asset.status,
            source="manage",
            note=f"绑定标签 · {asset.name}",
            status=OperationStatus.CONFIRMED,
        )
        await session.commit()
        return op_row

    raise ValueError(f"不支持的类型: {entity_type}")


async def rebind_tag(
    session: AsyncSession,
    *,
    entity_type: str,
    record_id: int,
    rfid_tag_epc: str,
) -> dict:
    """换绑：将新 EPC 替换原标签。"""
    epc = _normalize_epc(rfid_tag_epc)

    if entity_type == InventoryEntityType.SLOT_MATERIAL:
        item, slot, part, cabinet = await _get_slot_material_row(session, record_id)
        await _assert_no_pending_slot_ops(session, slot.id)
        _assert_slot_not_pending_status(slot)
        old_epc = slot.rfid_tag_epc
        if not old_epc:
            raise ValueError("该格位尚未绑定标签，请使用绑定")
        if old_epc.upper() == epc:
            raise ValueError("新标签与当前标签相同")
        await check_epc_available(session, epc, exclude_slot_id=slot.id)
        slot.rfid_tag_epc = epc
        op_row = await _create_inventory_operation(
            session,
            operation="tag_rebind",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=epc,
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=item.quantity,
            quantity_change=0,
            quantity_after=item.quantity,
            slot_status=slot.status,
            source="manage",
            note=f"换绑标签 {old_epc} → {epc} · {slot.slot_code}",
            status=OperationStatus.CONFIRMED,
        )
        await session.commit()
        return op_row

    if entity_type == InventoryEntityType.ASSET:
        asset = await _get_asset(session, record_id)
        await _assert_no_pending_asset_ops(session, asset.id)
        old_epc = asset.rfid_tag_epc
        if not old_epc:
            raise ValueError("该物件尚未绑定标签，请使用绑定")
        if old_epc.upper() == epc:
            raise ValueError("新标签与当前标签相同")
        await check_epc_available(session, epc, exclude_asset_id=asset.id)
        asset.rfid_tag_epc = epc
        op_row = await _create_inventory_operation(
            session,
            operation="tag_rebind",
            entity_type=InventoryEntityType.ASSET,
            epc=epc,
            part_id=None,
            slot_id=None,
            cabinet_id=None,
            asset_id=asset.id,
            quantity_before=1 if asset.status == "in_stock" else 0,
            quantity_change=0,
            quantity_after=1 if asset.status == "in_stock" else 0,
            slot_status=asset.status,
            source="manage",
            note=f"换绑标签 {old_epc} → {epc} · {asset.name}",
            status=OperationStatus.CONFIRMED,
        )
        await session.commit()
        return op_row

    raise ValueError(f"不支持的类型: {entity_type}")


async def unbind_tag(
    session: AsyncSession,
    *,
    entity_type: str,
    record_id: int,
) -> dict:
    """解绑：清除 RFID，保留库存。"""
    if entity_type == InventoryEntityType.SLOT_MATERIAL:
        item, slot, part, cabinet = await _get_slot_material_row(session, record_id)
        await _assert_no_pending_slot_ops(session, slot.id)
        _assert_slot_not_pending_status(slot)
        old_epc = slot.rfid_tag_epc
        if not old_epc:
            raise ValueError("该格位未绑定标签")
        slot.rfid_tag_epc = None
        op_row = await _create_inventory_operation(
            session,
            operation="tag_unbind",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=old_epc,
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=item.quantity,
            quantity_change=0,
            quantity_after=item.quantity,
            slot_status=slot.status,
            source="manage",
            note=f"解绑标签 {old_epc} · {slot.slot_code}",
            status=OperationStatus.CONFIRMED,
        )
        await session.commit()
        return op_row

    if entity_type == InventoryEntityType.ASSET:
        asset = await _get_asset(session, record_id)
        await _assert_no_pending_asset_ops(session, asset.id)
        old_epc = asset.rfid_tag_epc
        if not old_epc:
            raise ValueError("该物件未绑定标签")
        asset.rfid_tag_epc = None
        op_row = await _create_inventory_operation(
            session,
            operation="tag_unbind",
            entity_type=InventoryEntityType.ASSET,
            epc=old_epc,
            part_id=None,
            slot_id=None,
            cabinet_id=None,
            asset_id=asset.id,
            quantity_before=1 if asset.status == "in_stock" else 0,
            quantity_change=0,
            quantity_after=1 if asset.status == "in_stock" else 0,
            slot_status=asset.status,
            source="manage",
            note=f"解绑标签 {old_epc} · {asset.name}",
            status=OperationStatus.CONFIRMED,
        )
        await session.commit()
        return op_row

    raise ValueError(f"不支持的类型: {entity_type}")


async def delete_inventory_record(
    session: AsyncSession,
    *,
    entity_type: str,
    record_id: int,
) -> dict:
    """删除库存：料盒物料删除 inventory_item；非标物件删除 asset 记录。"""
    if entity_type == InventoryEntityType.SLOT_MATERIAL:
        item, slot, part, cabinet = await _get_slot_material_row(session, record_id)
        await _assert_no_pending_slot_ops(session, slot.id)
        _assert_slot_not_pending_status(slot)
        qty = item.quantity
        old_epc = slot.rfid_tag_epc
        op_row = await _create_inventory_operation(
            session,
            operation="delete",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=old_epc,
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=qty,
            quantity_change=-qty,
            quantity_after=0,
            slot_status=SlotStatus.EMPTY,
            source="manage",
            note=f"删除库存 · {slot.slot_code} · {part.name}",
            status=OperationStatus.CONFIRMED,
        )
        await session.delete(item)
        slot.rfid_tag_epc = None
        slot.label = None
        slot.status = SlotStatus.EMPTY
        await _sync_cabinet_status(session, cabinet.id)
        await session.commit()
        return op_row

    if entity_type == InventoryEntityType.ASSET:
        asset = await _get_asset(session, record_id)
        await _assert_no_pending_asset_ops(session, asset.id)
        old_epc = asset.rfid_tag_epc
        in_stock = asset.status == "in_stock"
        op_row = await _create_inventory_operation(
            session,
            operation="delete",
            entity_type=InventoryEntityType.ASSET,
            epc=old_epc,
            part_id=None,
            slot_id=None,
            cabinet_id=None,
            asset_id=asset.id,
            quantity_before=1 if in_stock else 0,
            quantity_change=-1 if in_stock else 0,
            quantity_after=0,
            slot_status=asset.status,
            source="manage",
            note=f"删除物件 · {asset.name} ({asset.asset_code})",
            status=OperationStatus.CONFIRMED,
        )
        await session.delete(asset)
        await session.commit()
        return op_row

    raise ValueError(f"不支持的类型: {entity_type}")


__all__ = [
    "bind_tag",
    "delete_inventory_record",
    "rebind_tag",
    "unbind_tag",
]
