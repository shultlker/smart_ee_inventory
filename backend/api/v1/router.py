from fastapi import APIRouter

from backend.api.v1.assets import router as assets_router
from backend.api.v1.boms import router as boms_router
from backend.api.v1.bins import router as bins_router
from backend.api.v1.categories import router as categories_router
from backend.api.v1.components import router as components_router
from backend.api.v1.inventory import router as inventory_router
from backend.api.v1.rfid import router as rfid_router
from backend.api.v1.slots import router as slots_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(assets_router)
api_v1_router.include_router(boms_router)
api_v1_router.include_router(bins_router)
api_v1_router.include_router(categories_router)
api_v1_router.include_router(components_router)
api_v1_router.include_router(slots_router)
api_v1_router.include_router(inventory_router)
api_v1_router.include_router(rfid_router)
