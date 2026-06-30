from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RfidEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    epc: str
    rssi: int | None = None
    antenna: int | None = None
    slot_id: int | None = None
    cabinet_id: int | None = None
    created_at: datetime
