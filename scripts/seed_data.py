"""Seed data: minimal 3-slot test cabinet for RFID field validation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset, BinCabinet, BinSlot, InventoryItem, Part, PartCategory

# ---------------------------------------------------------------------------
# 分类（仅保留 3 条测试物料所需）
# ---------------------------------------------------------------------------

CATEGORIES: list[dict] = [
    {
        "code": "passive",
        "name": "被动元件",
        "children": [
            {"code": "resistor", "name": "电阻"},
            {"code": "capacitor", "name": "电容"},
        ],
    },
    {
        "code": "active",
        "name": "主动元件",
        "children": [
            {"code": "led", "name": "LED"},
        ],
    },
]

# ---------------------------------------------------------------------------
# 3 条测试物料
# ---------------------------------------------------------------------------

PARTS: list[dict] = [
    {
        "part_number": "TEST-R-10K",
        "name": "测试电阻 10kΩ",
        "category_code": "resistor",
        "package": "0603",
        "value": "10kΩ",
        "params": [],
    },
    {
        "part_number": "TEST-C-100N",
        "name": "陶瓷电容 100nF",
        "category_code": "capacitor",
        "package": "0805",
        "value": "100nF",
        "params": [],
    },
    {
        "part_number": "TEST-LED-RED",
        "name": "红色 LED",
        "category_code": "led",
        "package": "0805",
        "value": "Red",
        "params": [],
    },
]

CABINET = {
    "code": "BIN-TEST",
    "name": "RFID 测试料盒",
    "location": "实验室测试位",
    "row_count": 1,
    "col_count": 3,
    "layer_count": 1,
    "rfid_tag_epc": None,
}

# (slot_code, row, col, part_number, qty, min_stock, rfid_tag_epc)
# 三个现场标签 EPC：两格料盒物料 + 一条非标物件（见 DEMO_ASSETS）
SLOT_INVENTORY: list[tuple] = [
    ("T01-1-1", 1, 1, "TEST-R-10K", 100, 10, "E28011704000021CCCF9A58E"),
    ("T01-1-2", 1, 2, "TEST-C-100N", 200, 20, "E28068940000502244813C7D"),
    ("T01-1-3", 1, 3, "TEST-LED-RED", 150, 15, None),
]

DEMO_ASSETS: list[dict] = [
    {
        "asset_code": "AST-0001",
        "name": "Jetson Nano 开发板",
        "category": "dev_board",
        "rfid_tag_epc": "E28011704000021CCCF9A59E",
        "status": "in_stock",
        "location": "实验室测试位",
        "remark": "EPC E28011704000021CCCF9A59E",
    },
]


async def _get_or_create_category(
    session: AsyncSession,
    code: str,
    name: str,
    parent_id: int | None = None,
) -> PartCategory:
    result = await session.execute(select(PartCategory).where(PartCategory.code == code))
    cat = result.scalar_one_or_none()
    if cat:
        return cat
    cat = PartCategory(code=code, name=name, parent_id=parent_id)
    session.add(cat)
    await session.flush()
    return cat


async def seed_categories(session: AsyncSession) -> dict[str, PartCategory]:
    index: dict[str, PartCategory] = {}
    for group in CATEGORIES:
        parent = await _get_or_create_category(session, group["code"], group["name"])
        index[parent.code] = parent
        for child in group.get("children", []):
            cat = await _get_or_create_category(
                session, child["code"], child["name"], parent_id=parent.id
            )
            index[cat.code] = cat
    return index


async def seed_parts(session: AsyncSession, categories: dict[str, PartCategory]) -> dict[str, Part]:
    index: dict[str, Part] = {}
    for item in PARTS:
        result = await session.execute(select(Part).where(Part.part_number == item["part_number"]))
        existing = result.scalar_one_or_none()
        if existing:
            index[existing.part_number] = existing
            continue

        cat = categories.get(item["category_code"])
        part = Part(
            part_number=item["part_number"],
            name=item["name"],
            category_id=cat.id if cat else None,
            manufacturer=item.get("manufacturer"),
            manufacturer_part_number=item.get("manufacturer_part_number"),
            package=item.get("package"),
            footprint=item.get("footprint"),
            value=item.get("value"),
            tolerance=item.get("tolerance"),
            voltage_rating=item.get("voltage_rating"),
            current_rating=item.get("current_rating"),
            power_rating=item.get("power_rating"),
            material=item.get("material"),
            thread_spec=item.get("thread_spec"),
            length_mm=item.get("length_mm"),
        )
        session.add(part)
        await session.flush()
        index[part.part_number] = part
    return index


async def seed_cabinet_and_slots(session: AsyncSession) -> tuple[BinCabinet, dict[str, BinSlot]]:
    result = await session.execute(select(BinCabinet).where(BinCabinet.code == CABINET["code"]))
    cabinet = result.scalar_one_or_none()
    if not cabinet:
        cabinet = BinCabinet(**CABINET)
        session.add(cabinet)
        await session.flush()
    else:
        for key, value in CABINET.items():
            setattr(cabinet, key, value)

    slots: dict[str, BinSlot] = {}
    for slot_code, row, col, _, _, _, epc in SLOT_INVENTORY:
        result = await session.execute(
            select(BinSlot).where(
                BinSlot.cabinet_id == cabinet.id,
                BinSlot.slot_code == slot_code,
            )
        )
        slot = result.scalar_one_or_none()
        slot_status = "occupied"
        if not slot:
            slot = BinSlot(
                cabinet_id=cabinet.id,
                slot_code=slot_code,
                row_no=row,
                col_no=col,
                layer_no=1,
                status=slot_status,
                rfid_tag_epc=epc,
            )
            session.add(slot)
            await session.flush()
        else:
            slot.row_no = row
            slot.col_no = col
            slot.status = slot_status
            slot.rfid_tag_epc = epc
        slots[slot_code] = slot
    return cabinet, slots


async def seed_inventory(
    session: AsyncSession,
    parts: dict[str, Part],
    slots: dict[str, BinSlot],
) -> None:
    for slot_code, _, _, part_number, qty, min_stock, _epc in SLOT_INVENTORY:
        part = parts[part_number]
        slot = slots[slot_code]
        result = await session.execute(
            select(InventoryItem).where(
                InventoryItem.part_id == part.id,
                InventoryItem.slot_id == slot.id,
                InventoryItem.batch_no.is_(None),
            )
        )
        item = result.scalar_one_or_none()
        if item:
            item.quantity = qty
            item.min_stock = min_stock
            item.reorder_point = min_stock
            item.status = "low_stock" if qty <= min_stock else "in_stock"
            continue
        status = "low_stock" if qty <= min_stock else "in_stock"
        session.add(
            InventoryItem(
                part_id=part.id,
                slot_id=slot.id,
                quantity=qty,
                min_stock=min_stock,
                reorder_point=min_stock,
                status=status,
            )
        )


async def seed_demo_assets(session: AsyncSession) -> None:
    for item in DEMO_ASSETS:
        result = await session.execute(select(Asset).where(Asset.asset_code == item["asset_code"]))
        asset = result.scalar_one_or_none()
        if asset:
            for key, value in item.items():
                setattr(asset, key, value)
            continue
        session.add(Asset(**item))


async def seed_all(session: AsyncSession) -> None:
    categories = await seed_categories(session)
    parts = await seed_parts(session, categories)
    _, slots = await seed_cabinet_and_slots(session)
    await seed_inventory(session, parts, slots)
    await seed_demo_assets(session)
    await session.commit()
