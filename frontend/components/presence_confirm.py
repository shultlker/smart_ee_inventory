"""Shared confirm dialogs for pending take_out / return operations."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx
from nicegui import ui

from frontend.services import ApiClient

RefreshCallback = Callable[[], Awaitable[None] | None]


def _short_epc(epc: str | None, head: int = 10, tail: int = 6) -> str:
    if not epc:
        return "—"
    epc = epc.strip().upper()
    if len(epc) <= head + tail + 1:
        return epc
    return f"{epc[:head]}…{epc[-tail:]}"


def mount_presence_confirm_dialog(
    client: ApiClient,
    *,
    on_confirmed: RefreshCallback | None = None,
) -> dict[str, Any]:
    """Create take_out/return confirm dialog; return state dict with opener."""
    state: dict[str, Any] = {
        "dialog_open": False,
        "pending_op": None,
        "prompted_ids": set(),
    }

    dialog = ui.dialog().props("persistent")

    def _on_hide() -> None:
        state["dialog_open"] = False

    dialog.on("hide", _on_hide)

    with dialog:
        with ui.card().classes("p-4 w-full").style(
            "min-width: min(420px, 92vw); max-width: 520px; max-height: 90vh; overflow-y: auto"
        ):
            title = ui.label("").classes("text-h6")
            subtitle = ui.label("").classes("text-subtitle1 text-primary q-mt-xs")
            detail = ui.label("").classes("text-body2 text-grey-8 q-mt-sm")
            meta = ui.label("").classes("text-caption text-grey q-mb-md whitespace-pre-wrap")

            take_out_panel = ui.column().classes("w-full gap-1")
            return_panel = ui.column().classes("w-full gap-1")

            with take_out_panel:
                ui.label("请填写领用信息").classes("text-subtitle2 q-mb-xs")
                user_input = ui.input("使用人 *").classes("w-full").props("outlined dense")
                project_input = ui.input("使用项目 *").classes("w-full").props("outlined dense")
                take_note_input = ui.input("备注（可选）").classes("w-full").props("outlined dense")

            with return_panel:
                ui.label("请确认归还信息").classes("text-subtitle2 q-mb-xs")
                consumed_input = ui.number("库存消耗数量", value=0, min=0).classes("w-full").props(
                    "outlined dense"
                )
                ui.label("如有实际消耗请填写，无消耗保持 0").classes("text-caption text-grey q-mb-xs")
                return_note_input = ui.input("备注（可选）").classes("w-full").props("outlined dense")

            async def _refresh_parent() -> None:
                if on_confirmed:
                    result = on_confirmed()
                    if hasattr(result, "__await__"):
                        await result

            async def submit_confirm() -> None:
                op = state.get("pending_op")
                if not op:
                    dialog.close()
                    return
                op_id = op["id"]
                payload: dict[str, Any]
                if op.get("operation") == "take_out":
                    user = (user_input.value or "").strip()
                    project = (project_input.value or "").strip()
                    if not user or not project:
                        ui.notify("请填写使用人与使用项目", type="warning")
                        return
                    payload = {
                        "take_out": {
                            "user_name": user,
                            "project_name": project,
                            "note": (take_note_input.value or "").strip() or None,
                        }
                    }
                else:
                    payload = {
                        "return_info": {
                            "consumed_qty": int(consumed_input.value or 0),
                            "note": (return_note_input.value or "").strip() or None,
                        }
                    }
                try:
                    await client.confirm_inventory_operation(op_id, payload)
                except httpx.HTTPStatusError as exc:
                    detail_msg = exc.response.text
                    try:
                        detail_msg = exc.response.json().get("detail", detail_msg)
                    except Exception:
                        pass
                    ui.notify(f"确认失败: {detail_msg}", type="negative")
                    return
                except Exception as exc:
                    ui.notify(f"确认失败: {exc}", type="negative")
                    return
                state["dialog_open"] = False
                state["pending_op"] = None
                dialog.close()
                ui.notify("操作已确认", type="positive")
                await _refresh_parent()

            async def cancel_pending() -> None:
                op = state.get("pending_op")
                if op:
                    try:
                        await client.cancel_inventory_operation(op["id"])
                    except Exception:
                        pass
                state["dialog_open"] = False
                state["pending_op"] = None
                dialog.close()
                await _refresh_parent()

            with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
                ui.button("取消", on_click=cancel_pending).props("flat")
                ui.button("确认", on_click=submit_confirm).props("color=primary")

    def _fill_meta(op: dict[str, Any]) -> None:
        lines: list[str] = []
        if op.get("cabinet_name") or op.get("cabinet_code"):
            lines.append(f"料盒: {op.get('cabinet_code') or '—'} · {op.get('cabinet_name') or ''}".rstrip(" · "))
        if op.get("slot_code"):
            lines.append(f"格位: {op['slot_code']}")
        if op.get("part_number") or op.get("part_name"):
            lines.append(
                f"物料: {op.get('part_name') or '—'}（{op.get('part_number') or '—'}）"
            )
        if op.get("asset_code") or op.get("asset_name"):
            lines.append(f"物件: {op.get('asset_name') or '—'}（{op.get('asset_code') or '—'}）")
        if op.get("quantity_before") is not None:
            lines.append(f"当前库存: {op['quantity_before']}")
        if op.get("epc"):
            lines.append(f"EPC: {_short_epc(op.get('epc'))}")
        meta.set_text("\n".join(lines) if lines else "")

    def open_for_operation(op: dict[str, Any]) -> None:
        if state["dialog_open"]:
            return
        op_id = op.get("id")
        if op_id is not None and op_id in state["prompted_ids"]:
            return
        if op.get("status") != "pending":
            return

        state["pending_op"] = op
        state["dialog_open"] = True
        if op_id is not None:
            state["prompted_ids"].add(op_id)

        is_take_out = op.get("operation") == "take_out"
        take_out_panel.set_visibility(is_take_out)
        return_panel.set_visibility(not is_take_out)

        if op.get("entity_type") == "asset":
            name = op.get("asset_name") or op.get("asset_code") or "非标物件"
            if is_take_out:
                title.set_text("确认借出")
                subtitle.set_text(name)
                detail.set_text("检测到标签离开读卡区，请登记借用人与项目。")
            else:
                title.set_text("确认归还")
                subtitle.set_text(name)
                detail.set_text("检测到标签回到读卡区，请确认归还。")
        else:
            part = op.get("part_name") or op.get("part_number") or "—"
            slot = op.get("slot_code") or "—"
            cab = op.get("cabinet_code") or "—"
            if is_take_out:
                title.set_text("确认出库")
                subtitle.set_text(f"{cab} · {slot}")
                detail.set_text(f"物料 {part} 即将出库，请填写领用信息。")
            else:
                title.set_text("确认入库归还")
                subtitle.set_text(f"{cab} · {slot}")
                detail.set_text(f"物料 {part} 已回到读卡区，请填写消耗数量（如有）。")

        _fill_meta(op)

        user_input.value = ""
        project_input.value = ""
        take_note_input.value = ""
        consumed_input.value = 0
        return_note_input.value = ""
        dialog.open()

    state["open_for_operation"] = open_for_operation
    state["dialog"] = dialog
    return state
