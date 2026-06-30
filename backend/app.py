from fastapi import FastAPI

from backend.api import api_v1_router
from backend.core.lifespan import lifespan
from backend.ws import ws_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart EE Inventory API",
        description="智能电子元器件料盒系统 REST + WebSocket",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_v1_router)
    app.include_router(ws_router)
    return app
