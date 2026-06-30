from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.events import event_bus
from backend.models import (
    Asset,
    Bin,
    BinCabinet,
    BinSlot,
    Component,
    InventoryItem,
    InventoryOperation,
    InventoryTransaction,
    Part,
    PartCategory,
    RfidEvent,
)
from backend.schemas import (
    AssetRegister,
    BinCreate,
    BinSlotUpdate,
    BinUpdate,
    ComponentCreate,
    InventoryItemCreate,
    InventoryRegisterRequest,
)
from backend.services.epc_binding import check_epc_available, lookup_epc_binding
from backend.services.presence_watchdog import PresenceKind
from shared.constants import AssetStatus, EventType, InventoryEntityType


async def list_bins(session: AsyncSession) -> list[Bin]:
    result = await session.execute(select(Bin).order_by(Bin.code))
    return list(result.scalars().all())


async def get_bin(session: AsyncSession, bin_id: int) -> Bin | None:
    return await session.get(Bin, bin_id)


async def create_bin(session: AsyncSession, data: BinCreate) -> Bin:
    bin_ = Bin(**data.model_dump())
    session.add(bin_)
    await session.commit()
    await session.refresh(bin_)
    return bin_


async def update_bin(session: AsyncSession, bin_: Bin, data: BinUpdate) -> Bin:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(bin_, key, value)
    await session.commit()
    await session.refresh(bin_)
    return bin_


async def delete_bin(session: AsyncSession, bin_: Bin) -> None:
    await session.delete(bin_)
    await session.commit()


async def list_part_categories(session: AsyncSession) -> list[PartCategory]:
    result = await session.execute(
        select(PartCategory).order_by(PartCategory.sort_order, PartCategory.name)
    )
    return list(result.scalars().all())


async def list_components(session: AsyncSession) -> list[Component]:
    result = await session.execute(
        select(Component)
        .options(selectinload(Component.category))
        .order_by(Component.part_number)
    )
    return list(result.scalars().all())


async def create_component(session: AsyncSession, data: ComponentCreate) -> Component:
    part_number = data.part_number.strip()
    name = data.name.strip()
    if not part_number:
        raise ValueError("料号不能为空")
    if not name:
        raise ValueError("名称不能为空")
    if data.category_id is not None:
        category = await session.get(PartCategory, data.category_id)
        if category is None:
            raise ValueError(f"分类 ID {data.category_id} 不存在")

    existing = await session.execute(
        select(Component).where(Component.part_number == part_number)
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"料号 {part_number} 已存在")

    component = Component(
        **{
            **data.model_dump(),
            "part_number": part_number,
            "name": name,
        }
    )
    session.add(component)
    await session.commit()
    result = await session.execute(
        select(Component)
        .options(selectinload(Component.category))
        .where(Component.id == component.id)
    )
    return result.scalar_one()


async def record_rfid_event(
    session: AsyncSession,
    epc: str,
    rssi: int | None = None,
    antenna: int | None = None,
    slot_id: int | None = None,
    cabinet_id: int | None = None,
) -> RfidEvent:
    event = RfidEvent(
        epc=epc,
        rssi=rssi,
        antenna=antenna,
        slot_id=slot_id,
        cabinet_id=cabinet_id,
    )
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return event


async def list_rfid_events(
    session: AsyncSession,
    *,
    limit: int = 50,
    after_id: int = 0,
) -> list[RfidEvent]:
    if after_id > 0:
        result = await session.execute(
            select(RfidEvent)
            .where(RfidEvent.id > after_id)
            .order_by(RfidEvent.id.asc())
            .limit(limit)
        )
    else:
        result = await session.execute(
            select(RfidEvent).order_by(RfidEvent.id.desc()).limit(limit)
        )
    return list(result.scalars().all())


def _operation_row(
    op: InventoryOperation,
    *,
    part: Part | None = None,
    slot: BinSlot | None = None,
    cabinet: BinCabinet | None = None,
    asset: Asset | None = None,
) -> dict:
    return {
        "id": op.id,
        "operation": op.operation,
        "entity_type": op.entity_type,
        "epc": op.epc,
        "part_id": op.part_id,
        "slot_id": op.slot_id,
        "cabinet_id": op.cabinet_id,
        "asset_id": op.asset_id,
        "quantity_before": op.quantity_before,
        "quantity_change": op.quantity_change,
        "quantity_after": op.quantity_after,
        "slot_status": op.slot_status,
        "status": op.status,
        "user_name": op.user_name,
        "project_name": op.project_name,
        "consumed_qty": op.consumed_qty,
        "source": op.source,
        "note": op.note,
        "created_at": op.created_at,
        "part_number": part.part_number if part else None,
        "part_name": part.name if part else None,
        "slot_code": slot.slot_code if slot else None,
        "cabinet_code": cabinet.code if cabinet else None,
        "cabinet_name": cabinet.name if cabinet else None,
        "asset_code": asset.asset_code if asset else None,
        "asset_name": asset.name if asset else None,
    }


async def _create_inventory_operation(
    session: AsyncSession,
    *,
    operation: str,
    entity_type: str = InventoryEntityType.SLOT_MATERIAL,
    epc: str | None,
    part_id: int | None,
    slot_id: int | None,
    cabinet_id: int | None,
    asset_id: int | None = None,
    quantity_before: int,
    quantity_change: int,
    quantity_after: int,
    slot_status: str | None,
    source: str,
    note: str | None,
    status: str = "confirmed",
    user_name: str | None = None,
    project_name: str | None = None,
    consumed_qty: int = 0,
) -> dict:
    op = InventoryOperation(
        operation=operation,
        entity_type=entity_type,
        epc=epc,
        part_id=part_id,
        slot_id=slot_id,
        cabinet_id=cabinet_id,
        asset_id=asset_id,
        quantity_before=quantity_before,
        quantity_change=quantity_change,
        quantity_after=quantity_after,
        slot_status=slot_status,
        status=status,
        user_name=user_name,
        project_name=project_name,
        consumed_qty=consumed_qty,
        source=source,
        note=note,
    )
    session.add(op)
    await session.flush()
    part = await session.get(Part, part_id) if part_id else None
    slot = await session.get(BinSlot, slot_id) if slot_id else None
    cabinet = await session.get(BinCabinet, cabinet_id) if cabinet_id else None
    asset = await session.get(Asset, asset_id) if asset_id else None
    return _operation_row(op, part=part, slot=slot, cabinet=cabinet, asset=asset)


async def list_inventory_operations(
    session: AsyncSession,
    *,
    limit: int = 50,
    after_id: int = 0,
    status: str | None = None,
    operation: str | None = None,
) -> list[dict]:
    stmt = (
        select(InventoryOperation, Part, BinSlot, BinCabinet, Asset)
        .outerjoin(Part, InventoryOperation.part_id == Part.id)
        .outerjoin(BinSlot, InventoryOperation.slot_id == BinSlot.id)
        .outerjoin(BinCabinet, InventoryOperation.cabinet_id == BinCabinet.id)
        .outerjoin(Asset, InventoryOperation.asset_id == Asset.id)
    )
    if status:
        stmt = stmt.where(InventoryOperation.status == status)
    if operation:
        stmt = stmt.where(InventoryOperation.operation == operation)
    if after_id > 0:
        stmt = stmt.where(InventoryOperation.id > after_id).order_by(InventoryOperation.id.asc())
    else:
        stmt = stmt.order_by(InventoryOperation.id.desc())
    stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    rows: list[dict] = []
    for op, part, slot, cabinet, asset in result.all():
        rows.append(_operation_row(op, part=part, slot=slot, cabinet=cabinet, asset=asset))
    if after_id <= 0:
        rows.reverse()
    return rows


async def apply_presence_transition(
    session: AsyncSession,
    epc: str,
    kind: PresenceKind,
) -> dict | None:
    """Apply watchdog appear/disappear; return operation row when inventory changes."""
    binding = await lookup_epc_binding(session, epc)
    if not binding.is_bound:
        return None

    if binding.entity_type == InventoryEntityType.SLOT_MATERIAL:
        return await _apply_slot_presence(session, epc, kind, binding.slot_id)
    return None


async def _apply_slot_presence(
    session: AsyncSession,
    epc: str,
    kind: PresenceKind,
    slot_id: int | None,
) -> dict | None:
    if slot_id is None:
        return None
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

    if kind == "disappear":
        qty_before = inv.quantity
        if qty_before <= 0:
            return None
        qty_after = qty_before - 1
        inv.quantity = qty_after
        if qty_after <= 0:
            inv.quantity = 0
            inv.status = "out_of_stock"
            slot.status = "empty"
        else:
            slot.status = "occupied"
            inv.status = "in_stock"

        session.add(
            InventoryTransaction(
                txn_type="out",
                part_id=part.id,
                slot_id=slot.id,
                quantity_before=qty_before,
                quantity_change=-1,
                quantity_after=inv.quantity,
                reference_type="watchdog",
                note=f"看门狗取出 EPC={epc.upper()}",
            )
        )
        op_row = await _create_inventory_operation(
            session,
            operation="take_out",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=epc.upper(),
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=qty_before,
            quantity_change=-1,
            quantity_after=inv.quantity,
            slot_status=slot.status,
            source="watchdog",
            note=f"标签离开读卡区，格位 {slot.slot_code}",
        )
        await session.commit()
        return op_row

    if kind == "appear":
        qty_before = inv.quantity
        qty_after = qty_before + 1
        inv.quantity = qty_after
        inv.status = "in_stock"
        slot.status = "occupied"

        session.add(
            InventoryTransaction(
                txn_type="in",
                part_id=part.id,
                slot_id=slot.id,
                quantity_before=qty_before,
                quantity_change=1,
                quantity_after=qty_after,
                reference_type="watchdog",
                note=f"看门狗归还 EPC={epc.upper()}",
            )
        )
        op_row = await _create_inventory_operation(
            session,
            operation="return",
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            epc=epc.upper(),
            part_id=part.id,
            slot_id=slot.id,
            cabinet_id=cabinet.id,
            quantity_before=qty_before,
            quantity_change=1,
            quantity_after=qty_after,
            slot_status=slot.status,
            source="watchdog",
            note=f"标签进入读卡区，格位 {slot.slot_code}",
        )
        await session.commit()
        return op_row

    return None


async def get_slot(session: AsyncSession, slot_id: int) -> BinSlot | None:
    return await session.get(BinSlot, slot_id)


async def update_slot(session: AsyncSession, slot: BinSlot, data: BinSlotUpdate) -> BinSlot:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(slot, key, value)
    await session.commit()
    await session.refresh(slot)
    return slot


async def list_slots(
    session: AsyncSession,
    *,
    cabinet_id: int | None = None,
) -> list[dict]:
    stmt = (
        select(BinSlot, BinCabinet, InventoryItem, Part)
        .join(BinCabinet, BinSlot.cabinet_id == BinCabinet.id)
        .outerjoin(InventoryItem, InventoryItem.slot_id == BinSlot.id)
        .outerjoin(Part, InventoryItem.part_id == Part.id)
        .order_by(BinSlot.cabinet_id, BinSlot.row_no, BinSlot.col_no, BinSlot.layer_no)
    )
    if cabinet_id is not None:
        stmt = stmt.where(BinSlot.cabinet_id == cabinet_id)

    result = await session.execute(stmt)
    by_id: dict[int, dict] = {}
    for slot, cabinet, inv, part in result.all():
        if slot.id not in by_id:
            by_id[slot.id] = {
                "id": slot.id,
                "cabinet_id": slot.cabinet_id,
                "slot_code": slot.slot_code,
                "row_no": slot.row_no,
                "col_no": slot.col_no,
                "layer_no": slot.layer_no,
                "rfid_tag_epc": slot.rfid_tag_epc,
                "status": slot.status,
                "label": slot.label,
                "max_capacity": slot.max_capacity,
                "cabinet_code": cabinet.code,
                "cabinet_name": cabinet.name,
                "part_number": None,
                "part_name": None,
                "quantity": None,
            }
        if inv and part and by_id[slot.id]["part_number"] is None:
            by_id[slot.id]["part_number"] = part.part_number
            by_id[slot.id]["part_name"] = part.name
            by_id[slot.id]["quantity"] = inv.quantity
    return list(by_id.values())


async def list_inventory_items(
    session: AsyncSession,
    *,
    cabinet_id: int | None = None,
    slot_id: int | None = None,
    low_stock_only: bool = False,
) -> list[dict]:
    stmt = (
        select(InventoryItem, Part, BinSlot, BinCabinet)
        .join(Part, InventoryItem.part_id == Part.id)
        .join(BinSlot, InventoryItem.slot_id == BinSlot.id)
        .join(BinCabinet, BinSlot.cabinet_id == BinCabinet.id)
        .order_by(BinCabinet.code, BinSlot.slot_code, Part.part_number)
    )
    if cabinet_id is not None:
        stmt = stmt.where(BinCabinet.id == cabinet_id)
    if slot_id is not None:
        stmt = stmt.where(BinSlot.id == slot_id)

    result = await session.execute(stmt)
    items: list[dict] = []
    for inv, part, slot, cabinet in result.all():
        available = max(0, inv.quantity - inv.reserved_qty)
        if low_stock_only and inv.quantity > inv.min_stock:
            continue
        items.append(
            {
                "id": inv.id,
                "part_id": inv.part_id,
                "slot_id": inv.slot_id,
                "quantity": inv.quantity,
                "reserved_qty": inv.reserved_qty,
                "min_stock": inv.min_stock,
                "max_stock": inv.max_stock,
                "reorder_point": inv.reorder_point,
                "batch_no": inv.batch_no,
                "status": inv.status,
                "updated_at": inv.updated_at,
                "part_number": part.part_number,
                "part_name": part.name,
                "part_package": part.package,
                "part_value": part.value,
                "slot_code": slot.slot_code,
                "cabinet_code": cabinet.code,
                "cabinet_name": cabinet.name,
                "available_qty": available,
                "rfid_tag_epc": slot.rfid_tag_epc,
            }
        )
    return items


def _slot_code_for(cabinet: BinCabinet, row_no: int, col_no: int, layer_no: int) -> str:
    code = cabinet.code
    prefix = code.removeprefix("BIN-") if code.startswith("BIN-") else code
    if layer_no > 1:
        return f"{prefix}-{row_no}-{col_no}-L{layer_no}"
    return f"{prefix}-{row_no}-{col_no}"


async def list_assets(session: AsyncSession) -> list[Asset]:
    result = await session.execute(select(Asset).order_by(Asset.asset_code))
    return list(result.scalars().all())


async def _next_asset_code(session: AsyncSession) -> str:
    result = await session.execute(select(Asset.asset_code).order_by(Asset.id.desc()).limit(1))
    last = result.scalar_one_or_none()
    if last and last.startswith("AST-"):
        try:
            n = int(last.split("-", 1)[1]) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"AST-{n:04d}"


async def register_asset_entry(session: AsyncSession, data: AssetRegister) -> dict:
    epc = data.rfid_tag_epc.strip().upper()
    await check_epc_available(session, epc)

    name = data.name.strip()
    asset_code = (data.asset_code or "").strip() or await _next_asset_code(session)
    existing = await session.execute(select(Asset).where(Asset.asset_code == asset_code))
    if existing.scalar_one_or_none():
        raise ValueError(f"资产编号 {asset_code} 已存在")

    asset = Asset(
        asset_code=asset_code,
        name=name,
        category=data.category or "other",
        rfid_tag_epc=epc,
        status=AssetStatus.IN_STOCK,
        serial_no=data.serial_no,
        location=data.location,
        remark=data.remark,
    )
    session.add(asset)
    await session.flush()

    op_row = await _create_inventory_operation(
        session,
        operation="register_in",
        entity_type=InventoryEntityType.ASSET,
        epc=epc,
        part_id=None,
        slot_id=None,
        cabinet_id=None,
        asset_id=asset.id,
        quantity_before=0,
        quantity_change=1,
        quantity_after=1,
        slot_status=asset.status,
        source="register",
        note=f"非标物件入库绑定 EPC={epc}",
    )
    await session.commit()
    await event_bus.publish(EventType.INVENTORY_OPERATION, op_row)

    await session.refresh(asset)
    return {
        "id": asset.id,
        "asset_code": asset.asset_code,
        "name": asset.name,
        "category": asset.category,
        "rfid_tag_epc": asset.rfid_tag_epc,
        "status": asset.status,
        "serial_no": asset.serial_no,
        "location": asset.location,
        "remark": asset.remark,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


async def register_inventory_bind(
    session: AsyncSession,
    data: InventoryRegisterRequest,
) -> dict:
    if data.bind_type == "asset":
        asset_data = AssetRegister(
            name=data.name or "",
            rfid_tag_epc=data.rfid_tag_epc,
            asset_code=data.asset_code,
            category=data.category,
            serial_no=data.serial_no,
            location=data.location,
            remark=data.remark,
        )
        asset_row = await register_asset_entry(session, asset_data)
        return {"bind_type": "asset", "slot_item": None, "asset": asset_row}

    slot_row = await register_inventory_entry(session, data.to_slot_create())
    return {"bind_type": "slot_material", "slot_item": slot_row, "asset": None}


async def _check_epc_available(
    session: AsyncSession,
    epc: str,
    *,
    exclude_slot_id: int | None = None,
) -> None:
    await check_epc_available(session, epc, exclude_slot_id=exclude_slot_id)


async def _get_or_create_slot(
    session: AsyncSession,
    cabinet: BinCabinet,
    *,
    slot_id: int | None,
    row_no: int,
    col_no: int,
    layer_no: int,
) -> BinSlot:
    if slot_id is not None:
        slot = await session.get(BinSlot, slot_id)
        if not slot or slot.cabinet_id != cabinet.id:
            raise ValueError("格位不存在或不属于所选料盒")
        return slot

    result = await session.execute(
        select(BinSlot).where(
            BinSlot.cabinet_id == cabinet.id,
            BinSlot.row_no == row_no,
            BinSlot.col_no == col_no,
            BinSlot.layer_no == layer_no,
        )
    )
    slot = result.scalar_one_or_none()
    if slot:
        return slot

    slot_code = _slot_code_for(cabinet, row_no, col_no, layer_no)
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code=slot_code,
        row_no=row_no,
        col_no=col_no,
        layer_no=layer_no,
        status="empty",
    )
    session.add(slot)
    await session.flush()
    return slot


async def register_inventory_entry(
    session: AsyncSession,
    data: InventoryItemCreate,
) -> dict:
    part = await session.get(Part, data.part_id)
    if not part:
        raise ValueError("物料不存在")

    cabinet = await session.get(BinCabinet, data.cabinet_id)
    if not cabinet:
        raise ValueError("料盒不存在")

    epc = data.rfid_tag_epc.strip().upper()
    slot = await _get_or_create_slot(
        session,
        cabinet,
        slot_id=data.slot_id,
        row_no=data.row_no,
        col_no=data.col_no,
        layer_no=data.layer_no,
    )

    await _check_epc_available(session, epc, exclude_slot_id=slot.id)

    if slot.rfid_tag_epc and slot.rfid_tag_epc.upper() != epc:
        raise ValueError(f"格位 {slot.slot_code} 已绑定其他 RFID 标签")

    inv_check = await session.execute(
        select(InventoryItem).where(InventoryItem.slot_id == slot.id)
    )
    if inv_check.scalar_one_or_none():
        raise ValueError(f"格位 {slot.slot_code} 已有库存记录，请选择空位或先清空")

    slot.rfid_tag_epc = epc
    slot.status = "occupied"
    slot.label = part.name

    item = InventoryItem(
        part_id=part.id,
        slot_id=slot.id,
        quantity=data.quantity,
        min_stock=data.min_stock,
        batch_no=data.batch_no,
        status="in_stock",
    )
    session.add(item)
    await session.flush()

    session.add(
        InventoryTransaction(
            txn_type="in",
            part_id=part.id,
            slot_id=slot.id,
            quantity_before=0,
            quantity_change=data.quantity,
            quantity_after=data.quantity,
            reference_type="register",
            note=f"RFID 绑定入库 EPC={epc}",
        )
    )
    await session.flush()

    op_row = await _create_inventory_operation(
        session,
        operation="register_in",
        entity_type=InventoryEntityType.SLOT_MATERIAL,
        epc=epc,
        part_id=part.id,
        slot_id=slot.id,
        cabinet_id=cabinet.id,
        quantity_before=0,
        quantity_change=data.quantity,
        quantity_after=data.quantity,
        slot_status=slot.status,
        source="register",
        note=f"入库绑定 EPC={epc}",
    )
    await session.commit()
    await event_bus.publish(EventType.INVENTORY_OPERATION, op_row)

    rows = await list_inventory_items(session, slot_id=slot.id)
    match = next((r for r in rows if r["id"] == item.id), None)
    if match:
        return match
    raise RuntimeError("库存条目创建后读取失败")
