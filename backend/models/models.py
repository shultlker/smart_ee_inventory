"""SQLite ORM models for electronic components, hardware, bins, inventory and BOM."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base


# ---------------------------------------------------------------------------
# 元件分类 & 物料主数据
# ---------------------------------------------------------------------------


class PartCategory(Base):
    """物料分类（电子元件 / 五金件等，支持树形）。"""

    __tablename__ = "part_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("part_categories.id"), nullable=True)
    description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    parent: Mapped[PartCategory | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[PartCategory]] = relationship(back_populates="parent")
    parts: Mapped[list[Part]] = relationship(back_populates="category")


class Part(Base):
    """物料主数据：电子元件 + 电气五金通用字段。"""

    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    manufacturer_part_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("part_categories.id"), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(16), default="pcs")

    # 封装 / 规格（电阻电容电感、IC、螺丝等）
    package: Mapped[str | None] = mapped_column(String(64), nullable=True)
    footprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tolerance: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voltage_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    power_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    temperature_range: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 五金件：材质、螺纹、尺寸
    material: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thread_spec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    length_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    weight_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    spec_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    datasheet_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[PartCategory | None] = relationship(back_populates="parts")
    params: Mapped[list[PartParam]] = relationship(back_populates="part", cascade="all, delete-orphan")
    inventory_items: Mapped[list[InventoryItem]] = relationship(back_populates="part")
    bom_lines: Mapped[list[BomLine]] = relationship(back_populates="part")


class PartParam(Base):
    """元件扩展参数（EAV），存放分类特有属性。"""

    __tablename__ = "part_params"
    __table_args__ = (UniqueConstraint("part_id", "param_key", name="uq_part_param_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    param_key: Mapped[str] = mapped_column(String(64))
    param_value: Mapped[str] = mapped_column(String(256))
    param_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    part: Mapped[Part] = relationship(back_populates="params")


# ---------------------------------------------------------------------------
# 料盒 & 格位
# ---------------------------------------------------------------------------


class BinCabinet(Base):
    """料盒 / 储物柜（可绑定 RFID）。"""

    __tablename__ = "bin_cabinets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rfid_tag_epc: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=1)
    col_count: Mapped[int] = mapped_column(Integer, default=1)
    layer_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active")
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    slots: Mapped[list[BinSlot]] = relationship(back_populates="cabinet", cascade="all, delete-orphan")


class BinSlot(Base):
    """料盒格位（最小存储单元，可独立绑定 RFID）。"""

    __tablename__ = "bin_slots"
    __table_args__ = (
        UniqueConstraint("cabinet_id", "slot_code", name="uq_cabinet_slot_code"),
        Index("ix_bin_slots_position", "cabinet_id", "row_no", "col_no", "layer_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cabinet_id: Mapped[int] = mapped_column(ForeignKey("bin_cabinets.id", ondelete="CASCADE"), index=True)
    slot_code: Mapped[str] = mapped_column(String(32))
    row_no: Mapped[int] = mapped_column(Integer, default=1)
    col_no: Mapped[int] = mapped_column(Integer, default=1)
    layer_no: Mapped[int] = mapped_column(Integer, default=1)
    rfid_tag_epc: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    max_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="empty")
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cabinet: Mapped[BinCabinet] = relationship(back_populates="slots")
    inventory_items: Mapped[list[InventoryItem]] = relationship(back_populates="slot")
    rfid_events: Mapped[list[RfidEvent]] = relationship(back_populates="slot")


# ---------------------------------------------------------------------------
# 库存
# ---------------------------------------------------------------------------


class InventoryItem(Base):
    """格位库存：某物料在某格位的数量与预警阈值。"""

    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("part_id", "slot_id", "batch_no", name="uq_inventory_part_slot_batch"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("bin_slots.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    reserved_qty: Mapped[int] = mapped_column(Integer, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    max_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reorder_point: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_stock")
    last_counted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    part: Mapped[Part] = relationship(back_populates="inventory_items")
    slot: Mapped[BinSlot] = relationship(back_populates="inventory_items")

    @property
    def available_qty(self) -> int:
        return max(0, self.quantity - self.reserved_qty)


class Asset(Base):
    """非标物件：工具、开发板、设备等（独立 RFID，非格位物料）。"""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    rfid_tag_epc: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="in_stock")
    serial_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InventoryTransaction(Base):
    """库存流水：入库 / 出库 / 调拨 / 盘点调整。"""

    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_type: Mapped[str] = mapped_column(String(16), index=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("bin_slots.id"), index=True)
    quantity_before: Mapped[int] = mapped_column(Integer, default=0)
    quantity_change: Mapped[int] = mapped_column(Integer)
    quantity_after: Mapped[int] = mapped_column(Integer, default=0)
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InventoryOperation(Base):
    """库存出入库操作记录（看门狗 / 入库绑定等业务入口）。"""

    __tablename__ = "inventory_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation: Mapped[str] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), default="slot_material", index=True)
    epc: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"), nullable=True, index=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("bin_slots.id"), nullable=True, index=True)
    cabinet_id: Mapped[int | None] = mapped_column(
        ForeignKey("bin_cabinets.id"), nullable=True, index=True
    )
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    quantity_before: Mapped[int] = mapped_column(Integer, default=0)
    quantity_change: Mapped[int] = mapped_column(Integer, default=0)
    quantity_after: Mapped[int] = mapped_column(Integer, default=0)
    slot_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="confirmed", index=True)
    user_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    consumed_qty: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(32), default="watchdog")
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    part: Mapped[Part | None] = relationship()
    slot: Mapped[BinSlot | None] = relationship()
    cabinet: Mapped[BinCabinet | None] = relationship()
    asset: Mapped[Asset | None] = relationship()


# ---------------------------------------------------------------------------
# BOM
# ---------------------------------------------------------------------------


class Bom(Base):
    """BOM 头：产品 / 项目物料清单。"""

    __tablename__ = "boms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lines: Mapped[list[BomLine]] = relationship(back_populates="bom", cascade="all, delete-orphan")


class BomLine(Base):
    """BOM 明细行。"""

    __tablename__ = "bom_lines"
    __table_args__ = (UniqueConstraint("bom_id", "line_no", name="uq_bom_line_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=1)
    unit: Mapped[str] = mapped_column(String(16), default="pcs")
    designators: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)

    bom: Mapped[Bom] = relationship(back_populates="lines")
    part: Mapped[Part] = relationship(back_populates="bom_lines")


# ---------------------------------------------------------------------------
# RFID 事件
# ---------------------------------------------------------------------------


class RfidEvent(Base):
    """RFID 读卡事件日志。"""

    __tablename__ = "rfid_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    epc: Mapped[str] = mapped_column(String(64), index=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    antenna: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("bin_slots.id"), nullable=True)
    cabinet_id: Mapped[int | None] = mapped_column(ForeignKey("bin_cabinets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    slot: Mapped[BinSlot | None] = relationship(back_populates="rfid_events")


# ---------------------------------------------------------------------------
# 向后兼容别名（旧 API 层可逐步迁移）
# ---------------------------------------------------------------------------

Bin = BinCabinet
Component = Part
