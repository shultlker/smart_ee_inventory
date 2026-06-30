from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InventoryOperationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation: str
    entity_type: str = "slot_material"
    status: str = "confirmed"
    epc: str | None = None
    part_id: int | None = None
    slot_id: int | None = None
    cabinet_id: int | None = None
    asset_id: int | None = None
    quantity_before: int
    quantity_change: int
    quantity_after: int
    slot_status: str | None = None
    user_name: str | None = None
    project_name: str | None = None
    consumed_qty: int = 0
    source: str
    note: str | None = None
    created_at: datetime
    part_number: str | None = None
    part_name: str | None = None
    slot_code: str | None = None
    cabinet_code: str | None = None
    cabinet_name: str | None = None
    asset_code: str | None = None
    asset_name: str | None = None


class TakeOutConfirm(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=64)
    project_name: str = Field(..., min_length=1, max_length=128)
    note: str | None = Field(None, max_length=256)


class ReturnConfirm(BaseModel):
    consumed_qty: int = Field(0, ge=0)
    note: str | None = Field(None, max_length=256)


class OperationConfirmRequest(BaseModel):
    take_out: TakeOutConfirm | None = None
    return_info: ReturnConfirm | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> OperationConfirmRequest:
        has_out = self.take_out is not None
        has_ret = self.return_info is not None
        if has_out == has_ret:
            raise ValueError("请提供 take_out 或 return_info 其中之一")
        return self
