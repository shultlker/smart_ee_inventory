from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_session
from backend.schemas import RfidEventRead
from backend.services import list_rfid_events
from config import get_settings

router = APIRouter(prefix="/rfid", tags=["rfid"])


@router.get("/status")
async def api_rfid_status(request: Request) -> dict:
    settings = get_settings()
    gateway = getattr(request.app.state, "gateway", None)
    connected = bool(gateway and gateway.connected)
    return {
        "enabled": settings.rfid_enabled,
        "connected": connected,
        "port": settings.rfid_serial_port if settings.rfid_enabled else None,
    }


@router.get("/events", response_model=list[RfidEventRead])
async def api_list_rfid_events(
    limit: int = Query(50, ge=1, le=200),
    after_id: int = Query(0, ge=0, description="仅返回 id 大于此值的新事件"),
    session: AsyncSession = Depends(get_session),
) -> list[RfidEventRead]:
    events = await list_rfid_events(session, limit=limit, after_id=after_id)
    if after_id == 0:
        events = list(reversed(events))
    return [RfidEventRead.model_validate(e) for e in events]
