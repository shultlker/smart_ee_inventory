from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BinSlotUpdate(BaseModel):
    rfid_tag_epc: str | None = None
    label: str | None = None
    status: str | None = None
    max_capacity: int | None = None


class BinSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cabinet_id: int
    slot_code: str
    row_no: int
    col_no: int
    layer_no: int
    rfid_tag_epc: str | None = None
    status: str
    label: str | None = None
    max_capacity: int | None = None
    cabinet_code: str | None = None
    cabinet_name: str | None = None
    part_number: str | None = None
    part_name: str | None = None
    quantity: int | None = None


class InventoryItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    part_id: int
    slot_id: int
    quantity: int
    reserved_qty: int
    min_stock: int
    max_stock: int | None = None
    reorder_point: int | None = None
    batch_no: str | None = None
    status: str
    updated_at: datetime
    part_number: str
    part_name: str
    part_package: str | None = None
    part_value: str | None = None
    slot_code: str
    cabinet_code: str
    cabinet_name: str
    available_qty: int
    rfid_tag_epc: str | None = None


class InventoryItemCreate(BaseModel):
    """新建库存：选定物料与格位，绑定 RFID 标签。"""

    part_id: int
    cabinet_id: int
    rfid_tag_epc: str = Field(..., min_length=4, max_length=64)
    quantity: int = Field(0, ge=0)
    min_stock: int = Field(0, ge=0)
    batch_no: str | None = None
    slot_id: int | None = None
    row_no: int = Field(1, ge=1, le=20)
    col_no: int = Field(1, ge=1, le=20)
    layer_no: int = Field(1, ge=1, le=10)
