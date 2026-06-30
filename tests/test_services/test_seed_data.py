"""Tests for demo seed data."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset, BinCabinet, BinSlot, InventoryItem, Part
from scripts.seed_data import DEMO_ASSETS, SLOT_INVENTORY, seed_all


@pytest.mark.asyncio
async def test_seed_all_creates_bin_test_and_epcs(db_session: AsyncSession) -> None:
    await seed_all(db_session)

    cabinet = (
        await db_session.execute(select(BinCabinet).where(BinCabinet.code == "BIN-TEST"))
    ).scalar_one()
    assert cabinet.row_count == 1
    assert cabinet.col_count == 3

    slot_count = (
        await db_session.execute(
            select(func.count()).select_from(BinSlot).where(BinSlot.cabinet_id == cabinet.id)
        )
    ).scalar_one()
    assert slot_count == 3

    part_count = (await db_session.execute(select(func.count()).select_from(Part))).scalar_one()
    assert part_count >= 3

    for part_number in ("TEST-R-10K", "TEST-C-100N", "TEST-LED-RED"):
        row = (
            await db_session.execute(select(Part).where(Part.part_number == part_number))
        ).scalar_one_or_none()
        assert row is not None, part_number

    inv_count = (await db_session.execute(select(func.count()).select_from(InventoryItem))).scalar_one()
    assert inv_count >= 3

    slot_codes = (
        await db_session.execute(
            select(BinSlot.slot_code).where(BinSlot.cabinet_id == cabinet.id)
        )
    ).scalars().all()
    assert set(slot_codes) >= {"T01-1-1", "T01-1-2", "T01-1-3"}

    assets = (
        await db_session.execute(select(Asset).where(Asset.asset_code == "AST-0001"))
    ).scalar_one_or_none()
    assert assets is not None
    assert assets.rfid_tag_epc == DEMO_ASSETS[0]["rfid_tag_epc"]

    bound_epcs = {
        epc for _, _, _, _, _, _, epc in SLOT_INVENTORY if epc
    } | {a["rfid_tag_epc"] for a in DEMO_ASSETS}
    slots = (await db_session.execute(select(BinSlot.rfid_tag_epc))).scalars().all()
    slot_epcs = {e for e in slots if e}
    asset_rows = (await db_session.execute(select(Asset.rfid_tag_epc))).scalars().all()
    asset_epcs = {e for e in asset_rows if e}
    assert bound_epcs <= slot_epcs | asset_epcs
