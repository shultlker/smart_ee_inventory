from __future__ import annotations

from nicegui import ui

_NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("仪表盘", "/", "dashboard"),
    ("料盒管理", "/bins", "inventory_2"),
    ("格位", "/slots", "grid_view"),
    ("库存", "/inventory", "list_alt"),
    ("BOM 分析", "/inventory/bom", "receipt_long"),
    ("操作记录", "/inventory/operations", "history"),
    ("入库绑定", "/inventory/register", "nfc"),
)


def _current_path() -> str:
    try:
        path = ui.context.client.request.url.path
    except Exception:
        return "/"
    return path.rstrip("/") or "/"


def _is_active(path: str) -> bool:
    current = _current_path()
    normalized = path.rstrip("/") or "/"
    if normalized == "/":
        return current == "/"
    return current == normalized or current.startswith(f"{normalized}/")


def _nav_button(label: str, path: str, icon: str, *, accent: bool = False) -> None:
    active = _is_active(path)

    if accent:
        btn = ui.button(
            label,
            on_click=lambda p=path: ui.navigate.to(p),
        ).props(f'no-caps unelevated dense icon="{icon}"')
        if active:
            btn.classes("bg-primary text-white")
        else:
            btn.classes("bg-primary text-white opacity-90 hover:opacity-100")
        return

    btn = ui.button(
        label,
        on_click=lambda p=path: ui.navigate.to(p),
    ).props(f'flat no-caps dense icon="{icon}"')

    if active:
        btn.classes(
            "text-primary font-medium bg-blue-1 rounded-lg px-3"
        ).style("text-decoration: none")
    else:
        btn.classes(
            "text-grey-8 rounded-lg px-3 hover:bg-grey-2"
        ).style("text-decoration: none")


def navbar() -> None:
    with ui.header().classes(
        "items-center justify-between px-6 py-1 bg-white text-grey-9 "
        "shadow-sm border-b border-grey-3"
    ).style("min-height: 52px"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("memory", size="sm").classes("text-primary")
            ui.label("智能电子元器件料盒系统").classes(
                "text-subtitle1 font-medium text-grey-9"
            )

        with ui.row().classes("items-center gap-1"):
            for label, path, icon in _NAV_ITEMS[:-1]:
                _nav_button(label, path, icon)
            _nav_button(*_NAV_ITEMS[-1], accent=True)
