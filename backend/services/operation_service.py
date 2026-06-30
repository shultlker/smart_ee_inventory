"""Pending presence actions and operation confirmation."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    Asset,
    BinCabinet,
    BinSlot,
    InventoryItem,
    InventoryOperation,
    InventoryTransaction,
    Part,
)
from backend.schemas import OperationConfirmRequest
from backend.schemas.operation import ReturnConfirm, TakeOutConfirm
from backend.services.epc_binding import lookup_epc_binding
from backend.services.inventory_service import (
    _create_inventory_operation,
    _operation_row,
)
from backend.services.presence_watchdog import PresenceKind
from shared.constants import (
    AssetStatus,
    BinStatus,
    InventoryEntityType,
    OperationStatus,
    SlotStatus,
)


async def _sync_cabinet_status(session: AsyncSession, cabinet_id: int) -> None:
    cabinet = await session.get(BinCabinet, cabinet_id)
    if not cabinet:
        return
    result = await session.execute(select(BinSlot).where(BinSlot.cabinet_id == cabinet_id))
    slots = list(result.scalars().all())
    if not slots:
        cabinet.status = BinStatus.ACTIVE
        return
    statuses = {s.status for s in slots}
    if SlotStatus.PENDING_CHECKOUT in statuses or SlotStatus.CHECKOUT_UNREGISTERED in statuses:
        cabinet.status = BinStatus.CHECKOUT_UNREGISTERED
    elif SlotStatus.PENDING_RETURN in statuses or SlotStatus.RETURN_UNREGISTERED in statuses:
        cabinet.status = BinStatus.RETURN_UNREGISTERED
    elif SlotStatus.CHECKED_OUT in statuses:
        cabinet.status = BinStatus.CHECKED_OUT
    elif all(s.status == SlotStatus.EMPTY for s in slots):
        cabinet.status = BinStatus.EMPTY
    else:
        cabinet.status = BinStatus.ACTIVE


async def _has_pending_operation(
    session: AsyncSession,
    *,
    slot_id: int | None = None,
    asset_id: int | None = None,
) -> bool:
    stmt = select(InventoryOperation.id).where(InventoryOperation.status == OperationStatus.PENDING)
    if slot_id is not None:
        stmt = stmt.where(InventoryOperation.slot_id == slot_id)
    if asset_id is not None:
        stmt = stmt.where(InventoryOperation.asset_id == asset_id)
    result = await session.execute(stmt.limit(1))
    return result.scalar_one_or_none() is not None


async def _get_slot_inventory(
    session: AsyncSession,
    slot_id: int,
) -> tuple[BinSlot, InventoryItem, Part, BinCabinet] | None:
    slot = await session.get(BinSlot, slot_id)
    if not slot:
        return None
    inv_result = await session.execute(
        select(InventoryItem, Part)
        .join(Part, InventoryItem.part_id == Part.id)
        .where(InventoryItem.slot_id == slot.id)
        .order_by(InventoryItem.id.desc())
        .limit(1)
    )
    row = inv_result.first()
    if not row:
        return None
    inv, part = row
    cabinet = await session.get(BinCabinet, slot.cabinet_id)
    if not cabinet:
        return None
    return slot, inv, part, cabinet


async def create_presence_pending_action(
    session: AsyncSession,
    epc: str,
    kind: PresenceKind,
) -> dict | None:
    binding = await lookup_epc_binding(session, epc)
    if not binding.is_bound:
        return None
    if binding.entity_type == InventoryEntityType.SLOT_MATERIAL:
        return await _pending_slot_action(session, epc, kind, binding.slot_id)
    # 非标物件不经过看门狗，改用手动读卡借还（manual_asset_take_out / manual_asset_return）
    return None


async def _pending_slot_action(
    session: AsyncSession,
    epc: str,
    kind: PresenceKind,
    slot_id: int | None,
) -> dict | None:
    if slot_id is None:
        return None
    if await _has_pending_operation(session, slot_id=slot_id):
        return None

    row = await _get_slot_inventory(session, slot_id)
    if not row:
        return None
    slot, inv, part, cabinet = row

    if kind == "disappear":
        if slot.status == SlotStatus.RETURN_UNREGISTERED:
            slot.status = SlotStatus.CHECKED_OUT
            await _sync_cabinet_status(session, cabinet.id)
            await session.commit()
            return None
        if slot.status != SlotStatus.OCCUPIED or inv.quantity <= 0:
            return None
        slot.status = SlotStatus.PENDING_CHECKOUT
        op_row = await _create_inventory_operation(
            session,
            operation="take_out",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=epc.upper(),
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=inv.quantity,
            quantity_change=0,
            quantity_after=inv.quantity,
            slot_status=slot.status,
            source="watchdog",
            note=f"待确认出库 · 格位 {slot.slot_code}",
            status=OperationStatus.PENDING,
        )
        await _sync_cabinet_status(session, cabinet.id)
        await session.commit()
        return op_row

    if kind == "appear":
        from_checkout_unregistered = slot.status == SlotStatus.CHECKOUT_UNREGISTERED
        if slot.status not in (
            SlotStatus.CHECKED_OUT,
            SlotStatus.PENDING_RETURN,
            SlotStatus.CHECKOUT_UNREGISTERED,
        ):
            return None
        slot.status = SlotStatus.PENDING_RETURN
        note = f"待确认入库 · 格位 {slot.slot_code}"
        if from_checkout_unregistered:
            note += " · from_checkout_unregistered"
        op_row = await _create_inventory_operation(
            session,
            operation="return",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=epc.upper(),
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=inv.quantity,
            quantity_change=0,
            quantity_after=inv.quantity,
            slot_status=slot.status,
            source="watchdog",
            note=note,
            status=OperationStatus.PENDING,
        )
        await _sync_cabinet_status(session, cabinet.id)
        await session.commit()
        return op_row

    return None


async def _get_asset_by_epc(session: AsyncSession, epc: str) -> Asset:
    binding = await lookup_epc_binding(session, epc)
    if binding.entity_type != InventoryEntityType.ASSET or binding.asset_id is None:
        raise ValueError("该标签未绑定非标物件")
    asset = await session.get(Asset, binding.asset_id)
    if not asset:
        raise ValueError("非标物件不存在")
    return asset


async def manual_asset_take_out(
    session: AsyncSession,
    epc: str,
    data: TakeOutConfirm,
) -> dict:
    """借出：操作员手动读卡一次并登记使用人/项目。"""
    asset = await _get_asset_by_epc(session, epc.strip().upper())
    if asset.status != AssetStatus.IN_STOCK:
        if asset.status == AssetStatus.CHECKED_OUT:
            raise ValueError("该物件已借出，请先归还")
        raise ValueError(f"当前状态不允许借出: {asset.status}")

    asset.status = AssetStatus.CHECKED_OUT
    user_name = data.user_name.strip()
    project_name = data.project_name.strip()
    op_row = await _create_inventory_operation(
        session,
        operation="take_out",
        entity_type=InventoryEntityType.ASSET,
        epc=asset.rfid_tag_epc,
        part_id=None,
        slot_id=None,
        cabinet_id=None,
        asset_id=asset.id,
        quantity_before=1,
        quantity_change=-1,
        quantity_after=0,
        slot_status=asset.status,
        source="manual_scan",
        note=data.note or f"借出 · {user_name} · {project_name}",
        status=OperationStatus.CONFIRMED,
        user_name=user_name,
        project_name=project_name,
    )
    await session.commit()
    return op_row


async def manual_asset_return(
    session: AsyncSession,
    epc: str,
    data: ReturnConfirm | None = None,
) -> dict:
    """归还：操作员手动读卡一次确认入库。"""
    asset = await _get_asset_by_epc(session, epc.strip().upper())
    if asset.status != AssetStatus.CHECKED_OUT:
        if asset.status == AssetStatus.IN_STOCK:
            raise ValueError("该物件已在库，无需归还")
        raise ValueError(f"当前状态不允许归还: {asset.status}")

    asset.status = AssetStatus.IN_STOCK
    note = (data.note if data else None) or "归还入库"
    op_row = await _create_inventory_operation(
        session,
        operation="return",
        entity_type=InventoryEntityType.ASSET,
        epc=asset.rfid_tag_epc,
        part_id=None,
        slot_id=None,
        cabinet_id=None,
        asset_id=asset.id,
        quantity_before=0,
        quantity_change=1,
        quantity_after=1,
        slot_status=asset.status,
        source="manual_scan",
        note=note,
        status=OperationStatus.CONFIRMED,
        consumed_qty=data.consumed_qty if data else 0,
    )
    await session.commit()
    return op_row


async def confirm_inventory_operation(
    session: AsyncSession,
    operation_id: int,
    data: OperationConfirmRequest,
) -> dict:
    op = await session.get(InventoryOperation, operation_id)
    if not op:
        raise ValueError("操作记录不存在")
    if op.status != OperationStatus.PENDING:
        raise ValueError("该操作已处理")

    if op.entity_type == InventoryEntityType.SLOT_MATERIAL:
        row = await _confirm_slot_operation(session, op, data)
    elif op.entity_type == InventoryEntityType.ASSET:
        row = await _confirm_asset_operation(session, op, data)
    else:
        raise ValueError("不支持的操作类型")

    await session.commit()
    return row


async def _confirm_slot_operation(
    session: AsyncSession,
    op: InventoryOperation,
    data: OperationConfirmRequest,
) -> dict:
    if op.slot_id is None:
        raise ValueError("格位信息缺失")
    row = await _get_slot_inventory(session, op.slot_id)
    if not row:
        raise ValueError("格位库存不存在")
    slot, inv, part, cabinet = row

    if op.operation == "take_out":
        if data.take_out is None:
            raise ValueError("出库需填写使用人与项目")
        qty_before = inv.quantity
        if qty_before <= 0:
            raise ValueError("库存不足，无法出库")
        qty_after = qty_before - 1
        inv.quantity = qty_after
        if qty_after <= 0:
            inv.quantity = 0
            inv.status = "out_of_stock"
            slot.status = SlotStatus.CHECKED_OUT if qty_before > 0 else SlotStatus.EMPTY
        else:
            slot.status = SlotStatus.CHECKED_OUT
            inv.status = "in_stock"

        session.add(
            InventoryTransaction(
                txn_type="out",
                part_id=part.id,
                slot_id=slot.id,
                quantity_before=qty_before,
                quantity_change=-1,
                quantity_after=inv.quantity,
                reference_type="operation",
                reference_id=op.id,
                operator=data.take_out.user_name,
                note=data.take_out.note or f"出库 {slot.slot_code}",
            )
        )
        op.quantity_before = qty_before
        op.quantity_change = -1
        op.quantity_after = inv.quantity
        op.user_name = data.take_out.user_name.strip()
        op.project_name = data.take_out.project_name.strip()
        op.note = data.take_out.note or f"出库 · {op.user_name} · {op.project_name}"
        op.slot_status = slot.status
        op.status = OperationStatus.CONFIRMED

    elif op.operation == "return":
        if data.return_info is None:
            raise ValueError("入库需填写消耗信息")
        consumed = data.return_info.consumed_qty
        qty_before = inv.quantity
        reconcile = bool(op.note and "from_checkout_unregistered" in op.note)
        if reconcile:
            qty_after = max(0, qty_before - consumed)
        else:
            qty_after = max(0, qty_before + 1 - consumed)
        qty_change = qty_after - qty_before
        inv.quantity = qty_after
        inv.status = "in_stock" if qty_after > 0 else "out_of_stock"
        slot.status = SlotStatus.OCCUPIED if qty_after > 0 else SlotStatus.EMPTY

        session.add(
            InventoryTransaction(
                txn_type="in" if qty_change >= 0 else "out",
                part_id=part.id,
                slot_id=slot.id,
                quantity_before=qty_before,
                quantity_change=qty_change,
                quantity_after=qty_after,
                reference_type="operation",
                reference_id=op.id,
                note=data.return_info.note or f"归还 {slot.slot_code}",
            )
        )
        op.quantity_before = qty_before
        op.quantity_change = qty_change
        op.quantity_after = qty_after
        op.consumed_qty = consumed
        if consumed > 0:
            op.note = data.return_info.note or f"归还 · 消耗 {consumed}"
        else:
            op.note = data.return_info.note or f"归还 · 无消耗"
        op.slot_status = slot.status
        op.status = OperationStatus.CONFIRMED
    else:
        raise ValueError(f"未知操作 {op.operation}")

    await _sync_cabinet_status(session, cabinet.id)
    await session.flush()
    return _operation_row(
        op,
        part=part,
        slot=slot,
        cabinet=cabinet,
    )


async def _confirm_asset_operation(
    session: AsyncSession,
    op: InventoryOperation,
    data: OperationConfirmRequest,
) -> dict:
    if op.asset_id is None:
        raise ValueError("资产信息缺失")
    asset = await session.get(Asset, op.asset_id)
    if not asset:
        raise ValueError("资产不存在")

    if op.operation == "take_out":
        if data.take_out is None:
            raise ValueError("借出需填写使用人与项目")
        asset.status = AssetStatus.CHECKED_OUT
        op.quantity_before = 1
        op.quantity_change = -1
        op.quantity_after = 0
        op.user_name = data.take_out.user_name.strip()
        op.project_name = data.take_out.project_name.strip()
        op.note = data.take_out.note or f"借出 · {op.user_name} · {op.project_name}"
        op.slot_status = asset.status
        op.status = OperationStatus.CONFIRMED

    elif op.operation == "return":
        if data.return_info is None:
            raise ValueError("归还需确认")
        asset.status = AssetStatus.IN_STOCK
        op.quantity_before = 0
        op.quantity_change = 1
        op.quantity_after = 1
        op.consumed_qty = data.return_info.consumed_qty
        op.note = data.return_info.note or "归还入库"
        op.slot_status = asset.status
        op.status = OperationStatus.CONFIRMED
    else:
        raise ValueError(f"未知操作 {op.operation}")

    await session.flush()
    return _operation_row(op, asset=asset)


async def cancel_inventory_operation(session: AsyncSession, operation_id: int) -> dict:
    op = await session.get(InventoryOperation, operation_id)
    if not op:
        raise ValueError("操作记录不存在")
    if op.status != OperationStatus.PENDING:
        raise ValueError("该操作已处理")

    if op.entity_type == InventoryEntityType.SLOT_MATERIAL and op.slot_id:
        slot = await session.get(BinSlot, op.slot_id)
        cabinet_id = op.cabinet_id
        if slot:
            if op.operation == "take_out":
                row = await _get_slot_inventory(session, slot.id)
                if row and row[1].quantity > 0:
                    slot.status = SlotStatus.CHECKOUT_UNREGISTERED
                else:
                    slot.status = SlotStatus.EMPTY
            elif op.operation == "return":
                slot.status = SlotStatus.RETURN_UNREGISTERED
        if cabinet_id:
            await _sync_cabinet_status(session, cabinet_id)
    elif op.entity_type == InventoryEntityType.ASSET and op.asset_id:
        asset = await session.get(Asset, op.asset_id)
        if asset:
            if op.operation == "take_out":
                asset.status = AssetStatus.IN_STOCK
            elif op.operation == "return":
                asset.status = AssetStatus.CHECKED_OUT

    op.status = OperationStatus.CANCELLED
    await session.flush()
    await session.commit()
    return _operation_row(op)


async def _reset_pending_slot_statuses(session: AsyncSession) -> None:
    result = await session.execute(
        select(BinSlot).where(
            BinSlot.status.in_(
                (
                    SlotStatus.PENDING_CHECKOUT,
                    SlotStatus.PENDING_RETURN,
                )
            )
        )
    )
    cabinet_ids: set[int] = set()
    for slot in result.scalars().all():
        cabinet_ids.add(slot.cabinet_id)
        if slot.status == SlotStatus.PENDING_CHECKOUT:
            row = await _get_slot_inventory(session, slot.id)
            if row and row[1].quantity > 0:
                slot.status = SlotStatus.CHECKOUT_UNREGISTERED
            else:
                slot.status = SlotStatus.EMPTY
        else:
            slot.status = SlotStatus.RETURN_UNREGISTERED
    for cabinet_id in cabinet_ids:
        await _sync_cabinet_status(session, cabinet_id)

    asset_result = await session.execute(
        select(Asset).where(
            Asset.status.in_(
                (AssetStatus.PENDING_CHECKOUT, AssetStatus.PENDING_RETURN),
            )
        )
    )
    for asset in asset_result.scalars().all():
        if asset.status == AssetStatus.PENDING_CHECKOUT:
            asset.status = AssetStatus.IN_STOCK
        else:
            asset.status = AssetStatus.CHECKED_OUT


async def clear_all_inventory_operations(session: AsyncSession) -> int:
    count_result = await session.execute(select(InventoryOperation.id))
    total = len(count_result.all())
    await _reset_pending_slot_statuses(session)
    await session.execute(delete(InventoryOperation))
    await session.commit()
    return total


__all__ = [
    "cancel_inventory_operation",
    "clear_all_inventory_operations",
    "confirm_inventory_operation",
    "create_presence_pending_action",
    "manual_asset_return",
    "manual_asset_take_out",
]
