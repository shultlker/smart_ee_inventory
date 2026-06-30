from __future__ import annotations

from pydantic import BaseModel, Field


class InventoryItemUpdate(BaseModel):
    quantity: int | None = Field(None, ge=0)
    min_stock: int | None = Field(None, ge=0)
    max_stock: int | None = Field(None, ge=0)
    reorder_point: int | None = Field(None, ge=0)
    batch_no: str | None = Field(None, max_length=64)
    note: str | None = Field(None, max_length=256)


class AssetRecordUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    category: str | None = Field(None, max_length=32)
    serial_no: str | None = Field(None, max_length=128)
    location: str | None = Field(None, max_length=128)
    remark: str | None = Field(None, max_length=256)
    note: str | None = Field(None, max_length=256)
