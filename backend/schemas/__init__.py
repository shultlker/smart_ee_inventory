from backend.schemas.bin import (
    BinCreate,
    BinRead,
    BinStatusEvent,
    BinUpdate,
    ComponentCreate,
    ComponentRead,
)
from backend.schemas.category import CategoryRead
from backend.schemas.asset import AssetRead, AssetRegister, AssetManualReturn, AssetManualTakeOut
from backend.schemas.inventory_edit import AssetRecordUpdate, InventoryItemUpdate
from backend.schemas.inventory_manage import TagBindRequest, TagRebindRequest, TagUnbindRequest
from backend.schemas.operation import InventoryOperationRead, OperationConfirmRequest
from backend.schemas.register import InventoryRegisterRequest, InventoryRegisterResult
from backend.schemas.rfid import RfidEventRead
from backend.schemas.slot import BinSlotRead, BinSlotUpdate, InventoryItemCreate, InventoryItemRead

__all__ = [
    "AssetManualReturn",
    "AssetManualTakeOut",
    "AssetRead",
    "AssetRegister",
    "BinCreate",
    "BinRead",
    "BinUpdate",
    "BinStatusEvent",
    "BinSlotRead",
    "BinSlotUpdate",
    "CategoryRead",
    "ComponentCreate",
    "ComponentRead",
    "InventoryItemRead",
    "InventoryItemCreate",
    "InventoryItemUpdate",
    "AssetRecordUpdate",
    "InventoryOperationRead",
    "OperationConfirmRequest",
    "InventoryRegisterRequest",
    "InventoryRegisterResult",
    "RfidEventRead",
    "TagBindRequest",
    "TagRebindRequest",
    "TagUnbindRequest",
]
