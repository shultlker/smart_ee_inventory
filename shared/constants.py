"""Shared constants and enums."""

from enum import StrEnum


class AssetStatus(StrEnum):
    IN_STOCK = "in_stock"
    CHECKED_OUT = "checked_out"
    MAINTENANCE = "maintenance"
    PENDING_CHECKOUT = "pending_checkout"
    PENDING_RETURN = "pending_return"


class BinStatus(StrEnum):
    ACTIVE = "active"
    CHECKED_OUT = "checked_out"
    CHECKOUT_UNREGISTERED = "checkout_unregistered"
    RETURN_UNREGISTERED = "return_unregistered"
    EMPTY = "empty"
    OCCUPIED = "occupied"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


BIN_STATUS_LABELS: dict[str, str] = {
    BinStatus.ACTIVE: "正常",
    BinStatus.CHECKED_OUT: "已出库",
    BinStatus.CHECKOUT_UNREGISTERED: "出库未登记",
    BinStatus.RETURN_UNREGISTERED: "未登记归还",
    BinStatus.EMPTY: "空闲",
    BinStatus.OCCUPIED: "在库",
    BinStatus.UNKNOWN: "未知",
    BinStatus.OFFLINE: "离线",
    "inactive": "停用",
    "maintenance": "维护",
}


class SlotStatus(StrEnum):
    EMPTY = "empty"
    OCCUPIED = "occupied"
    CHECKED_OUT = "checked_out"
    PENDING_CHECKOUT = "pending_checkout"
    PENDING_RETURN = "pending_return"
    CHECKOUT_UNREGISTERED = "checkout_unregistered"
    RETURN_UNREGISTERED = "return_unregistered"


SLOT_STATUS_LABELS: dict[str, str] = {
    SlotStatus.EMPTY: "空闲",
    SlotStatus.OCCUPIED: "在库",
    SlotStatus.CHECKED_OUT: "已出库",
    SlotStatus.PENDING_CHECKOUT: "待出库",
    SlotStatus.PENDING_RETURN: "待入库",
    SlotStatus.CHECKOUT_UNREGISTERED: "出库未登记",
    SlotStatus.RETURN_UNREGISTERED: "未登记归还",
    "disabled": "禁用",
}


class OperationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class EventType(StrEnum):
    TAG_READ = "tag_read"
    BIN_STATUS_CHANGED = "bin_status_changed"
    GATEWAY_CONNECTED = "gateway_connected"
    GATEWAY_DISCONNECTED = "gateway_disconnected"
    INVENTORY_OPERATION = "inventory_operation"
    PRESENCE_CONFIRM_REQUIRED = "presence_confirm_required"


class InventoryEntityType(StrEnum):
    SLOT_MATERIAL = "slot_material"
    BIN_CONTAINER = "bin_container"
    ASSET = "asset"
