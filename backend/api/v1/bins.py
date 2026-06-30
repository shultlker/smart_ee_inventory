from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.schemas import BinCreate, BinRead, BinUpdate
from backend.services import create_bin, delete_bin, get_bin, list_bins, update_bin

router = APIRouter(prefix="/bins", tags=["bins"])


@router.get("", response_model=list[BinRead])
async def api_list_bins(session: AsyncSession = Depends(get_session)) -> list[BinRead]:
    bins = await list_bins(session)
    return [BinRead.model_validate(b) for b in bins]


@router.get("/{bin_id}", response_model=BinRead)
async def api_get_bin(bin_id: int, session: AsyncSession = Depends(get_session)) -> BinRead:
    bin_ = await get_bin(session, bin_id)
    if not bin_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bin not found")
    return BinRead.model_validate(bin_)


@router.post("", response_model=BinRead, status_code=status.HTTP_201_CREATED)
async def api_create_bin(data: BinCreate, session: AsyncSession = Depends(get_session)) -> BinRead:
    bin_ = await create_bin(session, data)
    return BinRead.model_validate(bin_)


@router.patch("/{bin_id}", response_model=BinRead)
async def api_update_bin(
    bin_id: int, data: BinUpdate, session: AsyncSession = Depends(get_session)
) -> BinRead:
    bin_ = await get_bin(session, bin_id)
    if not bin_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bin not found")
    updated = await update_bin(session, bin_, data)
    return BinRead.model_validate(updated)


@router.delete("/{bin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_bin(bin_id: int, session: AsyncSession = Depends(get_session)) -> None:
    bin_ = await get_bin(session, bin_id)
    if not bin_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bin not found")
    await delete_bin(session, bin_)
