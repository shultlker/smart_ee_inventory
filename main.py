"""Smart EE Inventory — application entry point."""

from __future__ import annotations

import logging

import uvicorn

from backend import create_app
from config import get_settings
from config.network import resolve_listen_port
from frontend import register_pages
from nicegui import ui

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)


def build_app():
    app = create_app()
    register_pages()
    ui.run_with(app, title="智能电子元器件料盒系统")
    return app


app = build_app()


def main() -> None:
    settings = get_settings()
    port, used_fallback = resolve_listen_port(settings.app_host, settings.app_port)
    if used_fallback:
        logger.warning(
            "端口 %s 不可用（可能被其他程序占用），已自动改用 %s。"
            "可在 .env 中设置 APP_PORT 指定其他端口。",
            settings.app_port,
            port,
        )
        print(
            f"\n⚠  端口 {settings.app_port} 已被占用，服务改为监听 http://{settings.app_host}:{port}\n"
        )

    url = f"http://{settings.app_host}:{port}"
    print(f"启动服务: {url}  (API 文档: {url}/docs)\n")

    uvicorn_kwargs = {
        "host": settings.app_host,
        "port": port,
        "reload": settings.debug,
    }
    if settings.debug:
        uvicorn.run("main:app", **uvicorn_kwargs)
    else:
        uvicorn.run(app, **uvicorn_kwargs)


if __name__ == "__main__":
    main()
