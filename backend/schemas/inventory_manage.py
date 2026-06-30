from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


EntityType = Literal["slot_material", "asset"]


class InventoryManageRef(BaseModel):
    entity_type: EntityType
    record_id: int = Field(..., ge=1, description="inventory_item.id 或 asset.id")


class TagBindRequest(InventoryManageRef):
    rfid_tag_epc: str = Field(..., min_length=4, max_length=64)


class TagRebindRequest(TagBindRequest):
    """换绑：将新 EPC 绑定到已有标签的库存。"""


class TagUnbindRequest(InventoryManageRef):
    """解绑：清除 RFID，保留库存记录。"""
