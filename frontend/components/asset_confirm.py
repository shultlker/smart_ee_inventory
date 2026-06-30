"""Dialog for non-standard asset take-out / return on RFID read."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

import httpx
from nicegui import ui

from frontend.services import ApiClient

RefreshCallback = Callable[[], Awaitable[None] | None]

_ASSET_STATUS_LABELS = {
    "in_stock": "在库",
    "checked_out": "已借出",
    "maintenance": "维修中",
}


def _short_epc(epc: str | None, head: int = 10, tail: int = 6) -> str:
    if not epc:
        return "—"
    epc = epc.strip().upper()
    if len(epc) <= head + tail + 1:
        return epc
    return f"{epc[:head]}…{epc[-tail:]}"


def mount_asset_confirm_dialog(
    client: ApiClient,
    *,
    on_confirmed: RefreshCallback | None = None,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "dialog_open": False,
        "pending_asset": None,
        "pending_epc": "",
        "mode": "take_out",
        "prompted_at": {},
        "dismissed_epcs": set(),
    }

    dialog = ui.dialog()

    def _on_hide() -> None:
        state["dialog_open"] = False

    dialog.on("hide", _on_hide)

    with dialog:
        with ui.card().classes("p-4 w-full").style(
            "min-width: min(400px, 92vw); max-width: 480px"
        ):
            title = ui.label("非标物件").classes("text-h6")
            subtitle = ui.label("").classes("text-subtitle1 text-primary q-mt-xs")
            detail = ui.label("").classes("text-body2 text-grey-8 q-mt-sm")
            epc_label = ui.label("").classes("text-caption font-mono text-grey q-mb-sm")

            take_out_panel = ui.column().classes("w-full gap-1")
            return_panel = ui.column().classes("w-full gap-1")

            with take_out_panel:
                ui.label("借出信息").classes("text-subtitle2 q-mb-xs")
                user_input = ui.input("使用人 *").classes("w-full").props("outlined dense")
                project_input = ui.input("使用项目 *").classes("w-full").props("outlined dense")
                take_note_input = ui.input("备注（可选）").classes("w-full").props("outlined dense")

            with return_panel:
                ui.label("归还信息").classes("text-subtitle2 q-mb-xs")
                return_note_input = ui.input("备注（可选）").classes("w-full").props("outlined dense")

            async def _refresh_parent() -> None:
                if on_confirmed:
                    result = on_confirmed()
                    if hasattr(result, "__await__"):
                        await result

            async def submit() -> None:
                asset = state.get("pending_asset")
                epc = (state.get("pending_epc") or "").strip().upper()
                if not asset or not epc:
                    dialog.close()
                    return
                try:
                    if state["mode"] == "take_out":
                        user = (user_input.value or "").strip()
                        project = (project_input.value or "").strip()
                        if not user or not project:
                            ui.notify("请填写使用人与使用项目", type="warning")
                            return
                        await client.asset_take_out(
                            {
                                "rfid_tag_epc": epc,
                                "user_name": user,
                                "project_name": project,
                                "note": (take_note_input.value or "").strip() or None,
                            }
                        )
                        ui.notify(f"已借出: {asset.get('name')}", type="positive")
                    else:
                        await client.asset_return(
                            {
                                "rfid_tag_epc": epc,
                                "note": (return_note_input.value or "").strip() or None,
                            }
                        )
                        ui.notify(f"已归还: {asset.get('name')}", type="positive")
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text
                    try:
                        detail = exc.response.json().get("detail", detail)
                    except Exception:
                        pass
                    ui.notify(f"操作失败: {detail}", type="negative")
                    return
                except httpx.HTTPError as exc:
                    ui.notify(f"操作失败: {exc}", type="negative")
                    return

                state["dialog_open"] = False
                dialog.close()
                await _refresh_parent()

            def dismiss() -> None:
                epc = state.get("pending_epc", "")
                if epc:
                    state["dismissed_epcs"].add(epc)
                state["dialog_open"] = False
                dialog.close()

            with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
                ui.button("忽略", on_click=dismiss).props("flat")
                ui.button("确认", icon="check", on_click=submit).props("color=primary")

    def _should_prompt(epc: str) -> bool:
        if epc in state["dismissed_epcs"]:
            return False
        last = state["prompted_at"].get(epc, 0.0)
        if time.monotonic() - last < 2.0:
            return False
        return True

    async def open_for_tag(payload: dict) -> None:
        if state["dialog_open"]:
            return
        entity_type = payload.get("entity_type")
        asset_id = payload.get("asset_id")
        epc = (payload.get("epc") or "").strip().upper()
        if entity_type != "asset" or not asset_id or not epc:
            return
        if not _should_prompt(epc):
            return

        try:
            assets = await client.get_assets()
        except httpx.HTTPError:
            return
        asset = next((a for a in assets if a["id"] == asset_id), None)
        if not asset:
            return

        status = asset.get("status", "")
        if status == "in_stock":
            mode = "take_out"
            title.set_text("非标物件 · 借出")
        elif status == "checked_out":
            mode = "return"
            title.set_text("非标物件 · 归还")
        else:
            ui.notify(
                f"物件「{asset.get('name')}」当前状态为"
                f" {_ASSET_STATUS_LABELS.get(status, status)}，无法借还",
                type="warning",
            )
            return

        state["pending_asset"] = asset
        state["pending_epc"] = epc
        state["mode"] = mode
        state["prompted_at"][epc] = time.monotonic()
        state["dialog_open"] = True

        subtitle.set_text(f"{asset.get('asset_code')} · {asset.get('name')}")
        detail.set_text(
            f"状态: {_ASSET_STATUS_LABELS.get(status, status)}"
            + (f"  ·  {asset.get('location')}" if asset.get("location") else "")
        )
        epc_label.set_text(f"EPC: {_short_epc(epc)}")
        user_input.value = ""
        project_input.value = ""
        take_note_input.value = ""
        return_note_input.value = ""
        take_out_panel.set_visibility(mode == "take_out")
        return_panel.set_visibility(mode == "return")
        dialog.open()

    return {"open_for_tag": open_for_tag, "state": state}
