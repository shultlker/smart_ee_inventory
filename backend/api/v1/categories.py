from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.schemas import CategoryRead
from backend.services import list_part_categories

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
async def api_list_categories(
    session: AsyncSession = Depends(get_session),
) -> list[CategoryRead]:
    items = await list_part_categories(session)
    return [CategoryRead.model_validate(c) for c in items]
