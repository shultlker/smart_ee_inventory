from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.schemas import BinSlotRead, BinSlotUpdate, InventoryItemRead
from backend.services import get_slot, list_inventory_items, list_slots, update_slot

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("", response_model=list[BinSlotRead])
async def api_list_slots(
    cabinet_id: int | None = Query(None, description="按料盒 ID 筛选"),
    session: AsyncSession = Depends(get_session),
) -> list[BinSlotRead]:
    rows = await list_slots(session, cabinet_id=cabinet_id)
    return [BinSlotRead.model_validate(r) for r in rows]


@router.get("/{slot_id}", response_model=BinSlotRead)
async def api_get_slot(
    slot_id: int,
    session: AsyncSession = Depends(get_session),
) -> BinSlotRead:
    rows = await list_slots(session)
    match = next((r for r in rows if r["id"] == slot_id), None)
    if not match:
        slot = await get_slot(session, slot_id)
        if not slot:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
        rows = await list_slots(session, cabinet_id=slot.cabinet_id)
        match = next((r for r in rows if r["id"] == slot_id), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
    return BinSlotRead.model_validate(match)


@router.patch("/{slot_id}", response_model=BinSlotRead)
async def api_update_slot(
    slot_id: int,
    data: BinSlotUpdate,
    session: AsyncSession = Depends(get_session),
) -> BinSlotRead:
    slot = await get_slot(session, slot_id)
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
    await update_slot(session, slot, data)
    rows = await list_slots(session, cabinet_id=slot.cabinet_id)
    match = next((r for r in rows if r["id"] == slot_id), None)
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Slot not found")
    return BinSlotRead.model_validate(match)
