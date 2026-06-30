from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.schemas.asset import AssetRead
from backend.schemas.slot import InventoryItemCreate, InventoryItemRead


class InventoryRegisterRequest(BaseModel):
    """统一入库绑定：料盒物料或非标物件。"""

    bind_type: Literal["slot_material", "asset"] = "slot_material"
    rfid_tag_epc: str = Field(..., min_length=4, max_length=64)

    part_id: int | None = None
    cabinet_id: int | None = None
    quantity: int = Field(0, ge=0)
    min_stock: int = Field(0, ge=0)
    batch_no: str | None = None
    slot_id: int | None = None
    row_no: int = Field(1, ge=1, le=20)
    col_no: int = Field(1, ge=1, le=20)
    layer_no: int = Field(1, ge=1, le=10)

    name: str | None = Field(None, min_length=1, max_length=256)
    asset_code: str | None = Field(None, min_length=1, max_length=64)
    category: str = Field("other", max_length=32)
    serial_no: str | None = Field(None, max_length=128)
    location: str | None = Field(None, max_length=128)
    remark: str | None = Field(None, max_length=256)

    @model_validator(mode="after")
    def validate_by_bind_type(self) -> InventoryRegisterRequest:
        if self.bind_type == "slot_material":
            if self.part_id is None or self.cabinet_id is None:
                raise ValueError("料盒物料入库需指定 part_id 与 cabinet_id")
        elif self.bind_type == "asset":
            if not (self.name or "").strip():
                raise ValueError("非标物件入库需填写名称")
        return self

    def to_slot_create(self) -> InventoryItemCreate:
        return InventoryItemCreate(
            part_id=self.part_id,  # type: ignore[arg-type]
            cabinet_id=self.cabinet_id,  # type: ignore[arg-type]
            rfid_tag_epc=self.rfid_tag_epc,
            quantity=self.quantity,
            min_stock=self.min_stock,
            batch_no=self.batch_no,
            slot_id=self.slot_id,
            row_no=self.row_no,
            col_no=self.col_no,
            layer_no=self.layer_no,
        )


class InventoryRegisterResult(BaseModel):
    bind_type: str
    slot_item: InventoryItemRead | None = None
    asset: AssetRead | None = None
