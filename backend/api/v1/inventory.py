from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.core.events import event_bus
from backend.schemas import (
    AssetRecordUpdate,
    InventoryItemRead,
    InventoryItemUpdate,
    InventoryOperationRead,
    InventoryRegisterRequest,
    InventoryRegisterResult,
    OperationConfirmRequest,
    TagBindRequest,
    TagRebindRequest,
    TagUnbindRequest,
)
from backend.services import (
    bind_tag,
    cancel_inventory_operation,
    clear_all_inventory_operations,
    confirm_inventory_operation,
    create_presence_pending_action,
    delete_inventory_record,
    list_inventory_items,
    list_inventory_operations,
    rebind_tag,
    register_inventory_bind,
    unbind_tag,
    update_asset_record,
    update_inventory_item,
)
from shared.constants import EventType

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryItemRead])
async def api_list_inventory(
    cabinet_id: int | None = Query(None),
    slot_id: int | None = Query(None),
    low_stock_only: bool = Query(False),
    session: AsyncSession = Depends(get_session),
) -> list[InventoryItemRead]:
    rows = await list_inventory_items(
        session,
        cabinet_id=cabinet_id,
        slot_id=slot_id,
        low_stock_only=low_stock_only,
    )
    return [InventoryItemRead.model_validate(r) for r in rows]


@router.post("/register", response_model=InventoryRegisterResult, status_code=status.HTTP_201_CREATED)
async def api_register_inventory(
    data: InventoryRegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> InventoryRegisterResult:
    try:
        row = await register_inventory_bind(session, data)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return InventoryRegisterResult.model_validate(row)


@router.get("/operations", response_model=list[InventoryOperationRead])
async def api_list_inventory_operations(
    limit: int = Query(50, ge=1, le=500),
    after_id: int = Query(0, ge=0),
    status: str | None = Query(None),
    operation: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> list[InventoryOperationRead]:
    rows = await list_inventory_operations(
        session,
        limit=limit,
        after_id=after_id,
        status=status,
        operation=operation,
    )
    return [InventoryOperationRead.model_validate(r) for r in rows]


@router.post("/operations/{operation_id}/confirm", response_model=InventoryOperationRead)
async def api_confirm_inventory_operation(
    operation_id: int,
    data: OperationConfirmRequest,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await confirm_inventory_operation(session, operation_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)


@router.post("/operations/{operation_id}/cancel", response_model=InventoryOperationRead)
async def api_cancel_inventory_operation(
    operation_id: int,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await cancel_inventory_operation(session, operation_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return InventoryOperationRead.model_validate(row)


@router.delete("/operations", status_code=status.HTTP_200_OK)
async def api_clear_inventory_operations(
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    deleted = await clear_all_inventory_operations(session)
    return {"deleted": deleted}


@router.post("/manage/bind-tag", response_model=InventoryOperationRead, status_code=status.HTTP_201_CREATED)
async def api_bind_tag(
    data: TagBindRequest,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await bind_tag(
            session,
            entity_type=data.entity_type,
            record_id=data.record_id,
            rfid_tag_epc=data.rfid_tag_epc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)


@router.post("/manage/rebind-tag", response_model=InventoryOperationRead, status_code=status.HTTP_201_CREATED)
async def api_rebind_tag(
    data: TagRebindRequest,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await rebind_tag(
            session,
            entity_type=data.entity_type,
            record_id=data.record_id,
            rfid_tag_epc=data.rfid_tag_epc,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)


@router.post("/manage/unbind-tag", response_model=InventoryOperationRead, status_code=status.HTTP_201_CREATED)
async def api_unbind_tag(
    data: TagUnbindRequest,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await unbind_tag(
            session,
            entity_type=data.entity_type,
            record_id=data.record_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)


@router.delete("/manage/{entity_type}/{record_id}", response_model=InventoryOperationRead)
async def api_delete_inventory_record(
    entity_type: str,
    record_id: int,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    if entity_type not in ("slot_material", "asset"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的类型")
    try:
        row = await delete_inventory_record(
            session,
            entity_type=entity_type,
            record_id=record_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)


@router.patch("/items/{item_id}", response_model=InventoryOperationRead)
async def api_update_inventory_item(
    item_id: int,
    data: InventoryItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> InventoryOperationRead:
    try:
        row = await update_inventory_item(session, item_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await event_bus.publish(EventType.INVENTORY_OPERATION, row)
    return InventoryOperationRead.model_validate(row)
