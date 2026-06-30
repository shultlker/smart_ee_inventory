from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_code: str
    name: str
    category: str
    rfid_tag_epc: str | None = None
    status: str
    serial_no: str | None = None
    location: str | None = None
    remark: str | None = None
    created_at: datetime
    updated_at: datetime


class AssetRegister(BaseModel):
    """登记非标物件并绑定 RFID。"""

    name: str = Field(..., min_length=1, max_length=256)
    rfid_tag_epc: str = Field(..., min_length=4, max_length=64)
    asset_code: str | None = Field(None, min_length=1, max_length=64)
    category: str = Field("other", max_length=32)
    serial_no: str | None = Field(None, max_length=128)
    location: str | None = Field(None, max_length=128)
    remark: str | None = Field(None, max_length=256)


class AssetManualTakeOut(BaseModel):
    """手动读卡借出非标物件。"""

    rfid_tag_epc: str = Field(..., min_length=4, max_length=64)
    user_name: str = Field(..., min_length=1, max_length=64)
    project_name: str = Field(..., min_length=1, max_length=128)
    note: str | None = Field(None, max_length=256)


class AssetManualReturn(BaseModel):
    """手动读卡归还非标物件。"""

    rfid_tag_epc: str = Field(..., min_length=4, max_length=64)
    note: str | None = Field(None, max_length=256)
