from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BinBase(BaseModel):
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=128)
    location: str | None = None
    rfid_tag_epc: str | None = None
    status: str = "active"
    row_count: int = Field(1, ge=1, le=20)
    col_count: int = Field(1, ge=1, le=20)
    layer_count: int = Field(1, ge=1, le=10)
    remark: str | None = None


class BinCreate(BinBase):
    pass


class BinUpdate(BaseModel):
    name: str | None = None
    location: str | None = None
    rfid_tag_epc: str | None = None
    status: str | None = None
    row_count: int | None = Field(None, ge=1, le=20)
    col_count: int | None = Field(None, ge=1, le=20)
    layer_count: int | None = Field(None, ge=1, le=10)
    remark: str | None = None


class BinRead(BinBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ComponentBase(BaseModel):
    part_number: str = Field(..., max_length=64)
    name: str = Field(..., max_length=256)
    category_id: int | None = None
    manufacturer: str | None = Field(None, max_length=128)
    package: str | None = Field(None, max_length=64)
    value: str | None = Field(None, max_length=64)


class ComponentCreate(ComponentBase):
    pass


class ComponentRead(ComponentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_code: str | None = None
    category_name: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class BinStatusEvent(BaseModel):
    bin_id: int | None = None
    epc: str
    status: str
    rssi: int | None = None
    timestamp: datetime
