from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.models import Component
from backend.schemas import ComponentCreate, ComponentRead
from backend.services import create_component, list_components

router = APIRouter(prefix="/components", tags=["components"])


def _component_to_read(component: Component) -> ComponentRead:
    read = ComponentRead.model_validate(component)
    category = component.category
    if category is None:
        return read
    return read.model_copy(
        update={
            "category_code": category.code,
            "category_name": category.name,
        }
    )


@router.get("", response_model=list[ComponentRead])
async def api_list_components(
    session: AsyncSession = Depends(get_session),
) -> list[ComponentRead]:
    items = await list_components(session)
    return [_component_to_read(c) for c in items]


@router.post("", response_model=ComponentRead, status_code=201)
async def api_create_component(
    data: ComponentCreate, session: AsyncSession = Depends(get_session)
) -> ComponentRead:
    try:
        component = await create_component(session, data)
    except ValueError as exc:
        detail = str(exc)
        status = 409 if "已存在" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return _component_to_read(component)
