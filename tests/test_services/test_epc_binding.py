"""Tests for EPC binding resolution."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset, BinCabinet, BinSlot
from backend.services.epc_binding import check_epc_available, lookup_epc_binding
from shared.constants import InventoryEntityType, SlotStatus


@pytest.mark.asyncio
async def test_lookup_slot_epc(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(code="BIN-EPC", name="EPC", row_count=1, col_count=1)
    db_session.add(cabinet)
    await db_session.flush()
    slot = BinSlot(
        cabinet_id=cabinet.id,
        slot_code="E-1-1",
        row_no=1,
        col_no=1,
        layer_no=1,
        status=SlotStatus.OCCUPIED,
        rfid_tag_epc="EPC-SLOT-001",
    )
    db_session.add(slot)
    await db_session.commit()

    binding = await lookup_epc_binding(db_session, "epc-slot-001")
    assert binding.is_bound
    assert binding.entity_type == InventoryEntityType.SLOT_MATERIAL
    assert binding.slot_id == slot.id
    assert binding.cabinet_id == cabinet.id


@pytest.mark.asyncio
async def test_lookup_asset_epc(db_session: AsyncSession) -> None:
    asset = Asset(
        asset_code="AST-EPC",
        name="Tool",
        category="tool",
        rfid_tag_epc="EPC-ASSET-001",
        status="in_stock",
    )
    db_session.add(asset)
    await db_session.commit()

    binding = await lookup_epc_binding(db_session, "EPC-ASSET-001")
    assert binding.entity_type == InventoryEntityType.ASSET
    assert binding.asset_id == asset.id


@pytest.mark.asyncio
async def test_lookup_cabinet_epc(db_session: AsyncSession) -> None:
    cabinet = BinCabinet(
        code="BIN-CAB-EPC",
        name="Cab",
        row_count=1,
        col_count=1,
        rfid_tag_epc="EPC-CAB-001",
    )
    db_session.add(cabinet)
    await db_session.commit()

    binding = await lookup_epc_binding(db_session, "EPC-CAB-001")
    assert binding.entity_type == InventoryEntityType.BIN_CONTAINER
    assert binding.cabinet_id == cabinet.id


@pytest.mark.asyncio
async def test_lookup_unknown_epc(db_session: AsyncSession) -> None:
    binding = await lookup_epc_binding(db_session, "UNKNOWN-EPC")
    assert not binding.is_bound
    assert binding.entity_type is None


@pytest.mark.asyncio
async def test_check_epc_available_conflict(db_session: AsyncSession) -> None:
    asset = Asset(
        asset_code="AST-DUP",
        name="Dup",
        category="other",
        rfid_tag_epc="EPC-DUP",
        status="in_stock",
    )
    db_session.add(asset)
    await db_session.commit()

    with pytest.raises(ValueError, match="非标物件"):
        await check_epc_available(db_session, "EPC-DUP")


@pytest.mark.asyncio
async def test_check_epc_available_exclude_self(db_session: AsyncSession) -> None:
    asset = Asset(
        asset_code="AST-SELF",
        name="Self",
        category="other",
        rfid_tag_epc="EPC-SELF",
        status="in_stock",
    )
    db_session.add(asset)
    await db_session.commit()

    await check_epc_available(db_session, "EPC-SELF", exclude_asset_id=asset.id)
