from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class BomLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_no: int
    part_id: int
    quantity: Decimal
    unit: str
    designators: str | None = None
    is_optional: bool = False
    note: str | None = None
    part_number: str | None = None
    part_name: str | None = None


class BomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    version: str
    description: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    lines: list[BomLineRead] = Field(default_factory=list)


class BomImportRequest(BaseModel):
    csv_text: str = Field(..., min_length=1)


class BomPreviewRequest(BaseModel):
    csv_text: str = Field(..., min_length=1)
    kit_qty: int = Field(1, ge=1)


class BomSlotLocation(BaseModel):
    slot_id: int
    slot_code: str
    cabinet_id: int
    cabinet_code: str
    cabinet_name: str
    row_no: int
    col_no: int
    quantity: int
    available_qty: int


class BomLineAnalysis(BaseModel):
    line_no: int
    part_id: int | None = None
    part_number: str
    part_name: str | None = None
    required_qty: Decimal
    available_qty: int
    shortage_qty: Decimal
    status: str
    designators: str | None = None
    note: str | None = None
    is_optional: bool = False
    slots: list[BomSlotLocation] = Field(default_factory=list)


class BomAnalysisRead(BaseModel):
    bom_id: int | None = None
    bom_code: str
    bom_name: str
    version: str
    kit_qty: int = 1
    lines: list[BomLineAnalysis]
    summary: dict[str, int]
    highlight_slot_ids: list[int] = Field(default_factory=list)
