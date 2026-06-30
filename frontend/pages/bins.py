from __future__ import annotations

from nicegui import ui

from frontend.components import navbar
from frontend.constants.bin_status import bin_status_color, bin_status_label
from frontend.services import ApiClient
from shared.constants import BinStatus


@ui.page("/bins")
async def bins_page() -> None:
    navbar()
    ui.label("料盒管理").classes("text-h5 q-pa-md")

    client = ApiClient()
    edit_dialog = ui.dialog()
    delete_dialog = ui.dialog()
    form: dict[str, ui.element] = {}
    edit_id: dict[str, int | None] = {"id": None}
    delete_id: dict[str, int | None] = {"id": None}

    def _bin_form_fields() -> None:
        form["code"] = ui.input("编号").classes("w-full")
        form["name"] = ui.input("名称").classes("w-full")
        form["location"] = ui.input("位置").classes("w-full")
        form["rfid_tag_epc"] = ui.input("RFID EPC（料盒级）").classes("w-full")
        form["status"] = ui.select(
            {"active": "启用", "inactive": "停用", "maintenance": "维护"},
            value="active",
            label="状态",
        ).classes("w-full")
        with ui.row().classes("w-full gap-2"):
            form["row_count"] = ui.number("行数", value=1, min=1, max=20).classes("flex-1")
            form["col_count"] = ui.number("列数", value=1, min=1, max=20).classes("flex-1")
            form["layer_count"] = ui.number("层数", value=1, min=1, max=10).classes("flex-1")
        form["remark"] = ui.textarea("备注").classes("w-full")

    def _read_form(*, include_code: bool) -> dict:
        data: dict = {
            "name": form["name"].value,
            "location": form["location"].value or None,
            "rfid_tag_epc": form["rfid_tag_epc"].value or None,
            "status": form["status"].value,
            "row_count": int(form["row_count"].value or 1),
            "col_count": int(form["col_count"].value or 1),
            "layer_count": int(form["layer_count"].value or 1),
            "remark": form["remark"].value or None,
        }
        if include_code:
            data["code"] = form["code"].value
        return data

    def _fill_form(bin_: dict | None) -> None:
        if bin_ is None:
            form["code"].value = ""
            form["name"].value = ""
            form["location"].value = ""
            form["rfid_tag_epc"].value = ""
            form["status"].value = "active"
            form["row_count"].value = 1
            form["col_count"].value = 1
            form["layer_count"].value = 1
            form["remark"].value = ""
            form["code"].enable()
            return
        form["code"].value = bin_["code"]
        form["name"].value = bin_["name"]
        form["location"].value = bin_.get("location") or ""
        form["rfid_tag_epc"].value = bin_.get("rfid_tag_epc") or ""
        form["status"].value = bin_.get("status") or "active"
        form["row_count"].value = bin_.get("row_count", 1)
        form["col_count"].value = bin_.get("col_count", 1)
        form["layer_count"].value = bin_.get("layer_count", 1)
        form["remark"].value = bin_.get("remark") or ""
        form["code"].disable()

    with edit_dialog, ui.card().classes("p-4 w-96"):
        ui.label("料盒").classes("text-h6")
        _bin_form_fields()

        async def save_bin() -> None:
            try:
                if edit_id["id"] is None:
                    await client.create_bin(_read_form(include_code=True))
                    ui.notify("料盒已创建")
                else:
                    await client.update_bin(
                        edit_id["id"],
                        _read_form(include_code=False),
                    )
                    ui.notify("料盒已更新")
                edit_dialog.close()
                content.refresh()
            except Exception as exc:
                ui.notify(f"保存失败: {exc}", type="negative")

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("取消", on_click=edit_dialog.close).props("flat")
            ui.button("保存", on_click=save_bin)

    with delete_dialog, ui.card().classes("p-4"):
        ui.label("确认删除该料盒？").classes("text-h6")
        delete_label = ui.label("")

        async def confirm_delete() -> None:
            bid = delete_id["id"]
            if bid is None:
                return
            try:
                await client.delete_bin(bid)
                ui.notify("已删除")
                delete_dialog.close()
                content.refresh()
            except Exception as exc:
                ui.notify(f"删除失败: {exc}", type="negative")

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("取消", on_click=delete_dialog.close).props("flat")
            ui.button("删除", on_click=confirm_delete).props("color=negative")

    def open_create() -> None:
        edit_id["id"] = None
        _fill_form(None)
        edit_dialog.open()

    def open_edit(bin_: dict) -> None:
        edit_id["id"] = bin_["id"]
        _fill_form(bin_)
        edit_dialog.open()

    def open_delete(bin_: dict) -> None:
        delete_id["id"] = bin_["id"]
        delete_label.set_text(f"{bin_['code']} · {bin_['name']}")
        delete_dialog.open()

    @ui.refreshable
    async def content() -> None:
        bins = await client.get_bins()
        with ui.row().classes("q-px-md q-mb-md gap-2"):
            ui.button("新建料盒", on_click=open_create).props("color=primary")
            ui.link("格位视图", "/slots").classes("self-center")
        with ui.grid(columns=3).classes("w-full q-px-md gap-4"):
            for bin_ in bins:
                with ui.card().classes("p-4"):
                    ui.label(bin_["name"]).classes("text-h6")
                    ui.label(f"编号: {bin_['code']}")
                    ui.label(f"位置: {bin_.get('location') or '—'}")
                    ui.label(
                        f"规格: {bin_.get('row_count', 1)}×{bin_.get('col_count', 1)}×"
                        f"{bin_.get('layer_count', 1)}"
                    )
                    epc = bin_.get("rfid_tag_epc")
                    if epc:
                        ui.label(f"EPC: {epc}").classes("text-caption text-blue")
                    status = bin_.get("status", BinStatus.ACTIVE)
                    ui.badge(
                        bin_status_label(status),
                        color=bin_status_color(status),
                    )
                    with ui.row().classes("gap-1 q-mt-sm"):
                        ui.button(
                            "编辑",
                            on_click=lambda b=bin_: open_edit(b),
                        ).props("flat dense")
                        ui.button(
                            "删除",
                            on_click=lambda b=bin_: open_delete(b),
                        ).props("flat dense color=negative")

    await content()
    ui.button("刷新", on_click=content.refresh).classes("q-ma-md")
