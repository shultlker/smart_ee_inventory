"""Unified RFID EPC → inventory entity resolution."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset, BinCabinet, BinSlot
from shared.constants import InventoryEntityType


@dataclass(frozen=True, slots=True)
class EpcBinding:
    entity_type: str | None
    slot_id: int | None = None
    cabinet_id: int | None = None
    asset_id: int | None = None

    @property
    def is_bound(self) -> bool:
        return self.entity_type is not None


async def lookup_epc_binding(session: AsyncSession, epc: str) -> EpcBinding:
    epc = epc.strip().upper()
    if not epc:
        return EpcBinding(entity_type=None)

    slot_result = await session.execute(
        select(BinSlot.id, BinSlot.cabinet_id).where(BinSlot.rfid_tag_epc == epc)
    )
    row = slot_result.first()
    if row:
        return EpcBinding(
            entity_type=InventoryEntityType.SLOT_MATERIAL,
            slot_id=row.id,
            cabinet_id=row.cabinet_id,
        )

    asset_result = await session.execute(select(Asset.id).where(Asset.rfid_tag_epc == epc))
    asset_id = asset_result.scalar_one_or_none()
    if asset_id is not None:
        return EpcBinding(
            entity_type=InventoryEntityType.ASSET,
            asset_id=asset_id,
        )

    cab_result = await session.execute(select(BinCabinet.id).where(BinCabinet.rfid_tag_epc == epc))
    cabinet_id = cab_result.scalar_one_or_none()
    if cabinet_id is not None:
        return EpcBinding(
            entity_type=InventoryEntityType.BIN_CONTAINER,
            cabinet_id=cabinet_id,
        )

    return EpcBinding(entity_type=None)


async def check_epc_available(
    session: AsyncSession,
    epc: str,
    *,
    exclude_slot_id: int | None = None,
    exclude_asset_id: int | None = None,
    exclude_cabinet_id: int | None = None,
) -> None:
    epc = epc.strip().upper()

    slot_result = await session.execute(select(BinSlot).where(BinSlot.rfid_tag_epc == epc))
    slot = slot_result.scalar_one_or_none()
    if slot and slot.id != exclude_slot_id:
        raise ValueError(f"EPC 已被格位 {slot.slot_code} 占用")

    asset_result = await session.execute(select(Asset).where(Asset.rfid_tag_epc == epc))
    asset = asset_result.scalar_one_or_none()
    if asset and asset.id != exclude_asset_id:
        raise ValueError(f"EPC 已被非标物件 {asset.asset_code} 占用")

    cab_result = await session.execute(select(BinCabinet).where(BinCabinet.rfid_tag_epc == epc))
    cabinet = cab_result.scalar_one_or_none()
    if cabinet and cabinet.id != exclude_cabinet_id:
        raise ValueError(f"EPC 已被料盒 {cabinet.code} 占用")
