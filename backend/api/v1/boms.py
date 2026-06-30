from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.schemas.bom import (
    BomAnalysisRead,
    BomImportRequest,
    BomPreviewRequest,
    BomRead,
)
from backend.services.bom_service import (
    analyze_bom_by_id,
    get_bom,
    import_bom_csv,
    list_boms,
    preview_bom_csv,
)

router = APIRouter(prefix="/boms", tags=["boms"])


@router.get("", response_model=list[BomRead])
async def api_list_boms(session: AsyncSession = Depends(get_session)) -> list[BomRead]:
    rows = await list_boms(session)
    return [BomRead.model_validate({**r, "lines": []}) for r in rows]


@router.get("/{bom_id}", response_model=BomRead)
async def api_get_bom(bom_id: int, session: AsyncSession = Depends(get_session)) -> BomRead:
    row = await get_bom(session, bom_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BOM 不存在")
    return BomRead.model_validate(row)


@router.post("/import", response_model=BomRead, status_code=status.HTTP_201_CREATED)
async def api_import_bom(
    data: BomImportRequest,
    session: AsyncSession = Depends(get_session),
) -> BomRead:
    try:
        row = await import_bom_csv(session, data.csv_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BomRead.model_validate(row)


@router.post("/preview", response_model=BomAnalysisRead)
async def api_preview_bom(
    data: BomPreviewRequest,
    session: AsyncSession = Depends(get_session),
) -> BomAnalysisRead:
    try:
        row = await preview_bom_csv(session, data.csv_text, kit_qty=data.kit_qty)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BomAnalysisRead.model_validate(row)


@router.get("/{bom_id}/analysis", response_model=BomAnalysisRead)
async def api_analyze_bom(
    bom_id: int,
    kit_qty: int = Query(1, ge=1),
    session: AsyncSession = Depends(get_session),
) -> BomAnalysisRead:
    try:
        row = await analyze_bom_by_id(session, bom_id, kit_qty=kit_qty)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return BomAnalysisRead.model_validate(row)
