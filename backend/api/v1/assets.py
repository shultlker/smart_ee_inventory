from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.events import event_bus
from backend.db import get_session
from backend.schemas import AssetManualReturn, AssetManualTakeOut, AssetRead, AssetRecordUpdate, InventoryOperationRead
from backend.schemas.operation import ReturnConfirm, TakeOutConfirm
from backend.services import list_assets, update_asset_record
from backend.services.operation_service import manual_asset_return, manual_asset_take_out
from shared.constants import EventType

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetRead])
async def api_list_assets(
    session: AsyncSession = Depends(get_session),
) -> list[AssetRead]:
    assets = await list_assets(session)
    return [AssetRead.model_validate(a) for a in assets]


@router.post("/take-out", response_model=InventoryOperationRead, status_code=status.HTTP_201_CREATED)
async def api_asset_take_out(
    data: AssetManualTakeOut,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await manual_asset_take_out(
            session,
            data.rfid_tag_epc,
            TakeOutConfirm(
                user_name=data.user_name,
                project_name=data.project_name,
                note=data.note,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)


@router.post("/return", response_model=InventoryOperationRead, status_code=status.HTTP_201_CREATED)
async def api_asset_return(
    data: AssetManualReturn,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await manual_asset_return(
            session,
            data.rfid_tag_epc,
            ReturnConfirm(note=data.note),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)


@router.patch("/{asset_id}", response_model=InventoryOperationRead)
async def api_update_asset(
    asset_id: int,
    data: AssetRecordUpdate,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await update_asset_record(session, asset_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)
