from __future__ import annotations

from nicegui import ui

from frontend.components import navbar
from frontend.services import ApiClient


@ui.page("/slots")
async def slots_page() -> None:
    navbar()
    ui.label("格位视图").classes("text-h5 q-pa-md")

    client = ApiClient()
    bins = await client.get_bins()
    if not bins:
        ui.label("暂无料盒，请先在料盒管理中添加。").classes("q-pa-md text-grey")
        return

    cabinet_options = {b["name"]: b["id"] for b in bins}
    selected_name = next(iter(cabinet_options))
    cabinet_select = ui.select(
        cabinet_options,
        value=selected_name,
        label="选择料盒",
    ).classes("q-px-md")

    slot_dialog = ui.dialog()
    slot_form: dict[str, ui.element] = {}

    with slot_dialog, ui.card().classes("p-4 w-96"):
        ui.label("编辑格位").classes("text-h6")
        slot_form["code"] = ui.label("")
        slot_form["epc"] = ui.input("RFID EPC").classes("w-full")
        slot_form["label"] = ui.input("标签").classes("w-full")
        slot_form["status"] = ui.select(
            {
                "empty": "空闲",
                "occupied": "在库",
                "disabled": "禁用",
            },
            label="状态",
        ).classes("w-full")
        slot_id_holder: dict[str, int | None] = {"id": None}

        async def save_slot() -> None:
            sid = slot_id_holder["id"]
            if sid is None:
                return
            try:
                await client.update_slot(
                    sid,
                    {
                        "rfid_tag_epc": slot_form["epc"].value or None,
                        "label": slot_form["label"].value or None,
                        "status": slot_form["status"].value,
                    },
                )
                ui.notify("格位已更新")
                slot_dialog.close()
                grid.refresh()
            except Exception as exc:
                ui.notify(f"保存失败: {exc}", type="negative")

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("取消", on_click=slot_dialog.close).props("flat")
            ui.button("保存", on_click=save_slot)

    def open_slot_editor(slot: dict) -> None:
        slot_id_holder["id"] = slot["id"]
        slot_form["code"].set_text(f"格位: {slot['slot_code']}")
        slot_form["epc"].value = slot.get("rfid_tag_epc") or ""
        slot_form["label"].value = slot.get("label") or ""
        slot_form["status"].value = slot.get("status") or "empty"
        slot_dialog.open()

    @ui.refreshable
    async def grid() -> None:
        cabinet_id = cabinet_options.get(cabinet_select.value)
        if cabinet_id is None:
            return

        bin_ = next((b for b in bins if b["id"] == cabinet_id), None)
        if not bin_:
            return

        slots = await client.get_slots(cabinet_id=cabinet_id)
        slot_map = {(s["row_no"], s["col_no"]): s for s in slots}
        rows = bin_.get("row_count", 1)
        cols = bin_.get("col_count", 1)

        with ui.column().classes("q-px-md gap-2"):
            ui.label(
                f"{bin_['code']} · {bin_['name']}  ({rows}×{cols})"
            ).classes("text-subtitle1")
            with ui.grid(columns=cols).classes("w-full gap-2"):
                for r in range(1, rows + 1):
                    for c in range(1, cols + 1):
                        slot = slot_map.get((r, c))
                        with ui.card().classes("p-2 cursor-pointer min-h-24"):
                            if slot:
                                part = slot.get("part_number") or "—"
                                qty = slot.get("quantity")
                                qty_str = str(qty) if qty is not None else "—"
                                ui.label(slot["slot_code"]).classes("text-caption text-grey")
                                ui.label(part).classes("text-body2 truncate")
                                ui.label(f"数量: {qty_str}").classes("text-caption")
                                epc = slot.get("rfid_tag_epc")
                                if epc:
                                    ui.label(epc[:12] + "…").classes(
                                        "text-caption text-blue"
                                    )
                                ui.button(
                                    "编辑",
                                    on_click=lambda s=slot: open_slot_editor(s),
                                ).props("flat dense size=sm")
                            else:
                                ui.label(f"R{r}C{c}").classes("text-grey text-caption")
                                ui.label("未配置").classes("text-caption")

    await grid()
    cabinet_select.on("update:model-value", grid.refresh)

    ui.button("刷新", on_click=grid.refresh).classes("q-ma-md")
