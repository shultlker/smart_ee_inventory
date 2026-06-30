from __future__ import annotations

import httpx
from nicegui import ui

from frontend.components import navbar
from frontend.components.shelf_grid import render_shelf_grid
from frontend.services import ApiClient

_STATUS_LABEL = {
    "ok": "充足",
    "partial": "部分满足",
    "shortage": "缺货",
    "missing_part": "料号未建档",
    "optional_skip": "可选项跳过",
}

_STATUS_COLOR = {
    "ok": "green",
    "partial": "orange",
    "shortage": "red",
    "missing_part": "grey",
    "optional_skip": "blue-grey",
}

_SAMPLE_CSV = """bom_code,bom_name,version
DEMO-BOM-001,演示装配板卡,1.0
part_number,quantity,designators,note
TEST-R-10K,10,R1;R2;R3,主电路电阻
TEST-C-100N,5,C1;C2,滤波电容
TEST-LED-RED,3,D1;D2;D3,状态指示灯
"""


@ui.page("/inventory/bom")
async def inventory_bom_page() -> None:
    navbar()
    ui.label("BOM 分析与取料").classes("text-h5 q-pa-md")
    ui.label(
        "导入演示用 CSV 清单，按料号匹配库存并标出货柜格位。"
        "CSV 须包含 BOM 头信息与 part_number / quantity 明细列。"
    ).classes("q-px-md text-body2 text-grey-8 q-mb-md")

    client = ApiClient()
    state: dict = {
        "analysis": None,
        "bins": [],
        "selected_bin_id": None,
        "highlight_ids": set(),
    }

    with ui.row().classes("w-full q-px-md gap-4 items-start flex-wrap"):
        with ui.column().classes("flex-grow min-w-80 gap-3"):
            csv_input = (
                ui.textarea("BOM CSV", value=_SAMPLE_CSV)
                .classes("w-full font-mono text-sm")
                .props("outlined autogrow")
            )
            kit_qty_input = ui.number("装配套数", value=1, min=1, step=1).classes("w-32").props(
                "outlined dense"
            )

            with ui.row().classes("gap-2 flex-wrap"):
                preview_btn = ui.button("预览分析", icon="preview").props("outline")
                import_btn = ui.button("导入并保存", icon="upload")
                saved_select = ui.select(
                    label="已保存 BOM",
                    options={},
                    with_input=True,
                ).classes("min-w-48").props("outlined dense")

            summary_label = ui.label("").classes("text-body2 text-grey")
            error_label = ui.label("").classes("text-red")

            columns = [
                {"name": "line_no", "label": "行", "field": "line_no", "align": "left"},
                {"name": "part_number", "label": "料号", "field": "part_number", "align": "left"},
                {"name": "required_qty", "label": "需求", "field": "required_qty", "align": "right"},
                {"name": "available_qty", "label": "可用", "field": "available_qty", "align": "right"},
                {"name": "shortage_qty", "label": "缺口", "field": "shortage_qty", "align": "right"},
                {"name": "status", "label": "状态", "field": "status_label", "align": "left"},
                {"name": "slots", "label": "格位", "field": "slots_text", "align": "left"},
            ]
            analysis_table = ui.table(columns=columns, rows=[], row_key="line_no").classes("w-full")

        with ui.column().classes("flex-grow min-w-80 gap-2"):
            ui.label("货柜视图（蓝色高亮为 BOM 对应格位）").classes("text-subtitle1 q-mt-sm")
            bin_select = ui.select(label="选择料盒", options={}).classes("w-full").props(
                "outlined dense"
            )

            @ui.refreshable
            async def shelf_view() -> None:
                analysis = state["analysis"]
                if not analysis:
                    ui.label("请先预览或加载 BOM 分析结果。").classes("text-grey q-pa-md")
                    return
                bin_id = state["selected_bin_id"]
                if bin_id is None:
                    ui.label("请选择料盒以查看格位。").classes("text-grey q-pa-md")
                    return
                bin_ = next((b for b in state["bins"] if b["id"] == bin_id), None)
                if not bin_:
                    ui.label("料盒加载失败").classes("text-red q-pa-md")
                    return
                try:
                    slots = await client.get_slots(cabinet_id=bin_id)
                except httpx.HTTPError as exc:
                    ui.label(f"格位加载失败: {exc}").classes("text-red q-pa-md")
                    return
                cabinet_slot_ids = {s["id"] for s in slots}
                highlights = state["highlight_ids"] & cabinet_slot_ids
                render_shelf_grid(
                    bin_,
                    slots,
                    compact=True,
                    edit_link="/slots",
                    highlight_slot_ids=highlights,
                )

            await shelf_view()

    def _format_rows(analysis: dict) -> list[dict]:
        rows = []
        for line in analysis.get("lines", []):
            slots = line.get("slots") or []
            slots_text = "、".join(
                f"{s['cabinet_code']}/{s['slot_code']}({s['available_qty']})" for s in slots
            ) or "—"
            status = line.get("status", "")
            rows.append(
                {
                    **line,
                    "status_label": _STATUS_LABEL.get(status, status),
                    "slots_text": slots_text,
                }
            )
        return rows

    def _apply_analysis(analysis: dict) -> None:
        state["analysis"] = analysis
        state["highlight_ids"] = set(analysis.get("highlight_slot_ids") or [])
        analysis_table.rows = _format_rows(analysis)
        analysis_table.update()
        summary = analysis.get("summary") or {}
        summary_label.set_text(
            f"{analysis.get('bom_code')} · {analysis.get('bom_name')} v{analysis.get('version')} "
            f"× {analysis.get('kit_qty', 1)} 套 — "
            f"充足 {summary.get('ok', 0)} · 部分 {summary.get('partial', 0)} · "
            f"缺货 {summary.get('shortage', 0)} · 未建档 {summary.get('missing_part', 0)}"
        )
        error_label.set_text("")
        shelf_view.refresh()

    async def load_bins_and_boms() -> None:
        try:
            state["bins"] = await client.get_bins()
        except httpx.HTTPError:
            state["bins"] = []
        bin_options = {b["id"]: f"{b['code']} · {b['name']}" for b in state["bins"]}
        bin_select.options = bin_options
        if state["bins"] and state["selected_bin_id"] is None:
            state["selected_bin_id"] = state["bins"][0]["id"]
            bin_select.value = state["selected_bin_id"]

        try:
            boms = await client.list_boms()
        except httpx.HTTPError:
            boms = []
        saved_select.options = {b["id"]: f"{b['code']} · {b['name']}" for b in boms}

    async def on_preview() -> None:
        try:
            analysis = await client.preview_bom(
                {"csv_text": csv_input.value or "", "kit_qty": int(kit_qty_input.value or 1)}
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            error_label.set_text(f"预览失败: {detail}")
            return
        except httpx.HTTPError as exc:
            error_label.set_text(f"预览失败: {exc}")
            return
        _apply_analysis(analysis)

    async def on_import() -> None:
        try:
            bom = await client.import_bom({"csv_text": csv_input.value or ""})
            kit_qty = int(kit_qty_input.value or 1)
            analysis = await client.analyze_bom(bom["id"], kit_qty=kit_qty)
            await load_bins_and_boms()
            saved_select.value = bom["id"]
        except httpx.HTTPStatusError as exc:
            error_label.set_text(f"导入失败: {exc.response.text}")
            return
        except httpx.HTTPError as exc:
            error_label.set_text(f"导入失败: {exc}")
            return
        ui.notify(f"已导入 BOM {bom['code']}", type="positive")
        _apply_analysis(analysis)

    async def on_saved_bom_change() -> None:
        bom_id = saved_select.value
        if not bom_id:
            return
        try:
            analysis = await client.analyze_bom(int(bom_id), kit_qty=int(kit_qty_input.value or 1))
        except httpx.HTTPError as exc:
            error_label.set_text(f"分析失败: {exc}")
            return
        _apply_analysis(analysis)

    async def on_bin_change() -> None:
        state["selected_bin_id"] = bin_select.value
        shelf_view.refresh()

    preview_btn.on("click", on_preview)
    import_btn.on("click", on_import)
    saved_select.on("update:model-value", lambda: ui.timer(0.05, on_saved_bom_change, once=True))
    bin_select.on("update:model-value", lambda: ui.timer(0.05, on_bin_change, once=True))

    await load_bins_and_boms()
