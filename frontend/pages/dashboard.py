from __future__ import annotations

import time
from datetime import datetime

from nicegui import ui

from frontend.components import navbar
from frontend.components.shelf_grid import count_search_matches, render_shelf_grid
from frontend.constants.bin_status import bin_status_label
from frontend.services import ApiClient
from frontend.services.global_inventory_events import ensure_global_inventory_events

_OPERATION_LABELS = {
    "take_out": "取出",
    "return": "归还",
    "register_in": "入库",
    "tag_bind": "绑定标签",
    "tag_rebind": "换绑标签",
    "tag_unbind": "解绑标签",
    "delete": "删除库存",
    "manual_edit": "手动修改",
}
_ENTITY_LABELS = {
    "slot_material": "料盒物料",
    "asset": "非标物件",
    "bin_container": "料盒",
}

_ASSET_STATUS_LABELS = {
    "in_stock": "在库",
    "checked_out": "已借出",
    "maintenance": "维修中",
}


def _short_epc(epc: str, head: int = 12, tail: int = 6) -> str:
    epc = epc.strip().upper()
    if len(epc) <= head + tail + 1:
        return epc
    return f"{epc[:head]}…{epc[-tail:]}"


@ui.page("/")
async def dashboard_page() -> None:
    client = ApiClient()
    navbar(client=client)
    hub = ensure_global_inventory_events(client)
    cabinet_options: dict[str, int] = {}

    shelf_data: dict = {"bin": None, "slots": [], "error": None, "empty": False, "snapshot": None}
    assets_data: dict = {"rows": [], "error": None, "snapshot": None}
    shelf_loading = {"active": False}
    shelf_search = {"query": ""}
    bin_table_data: dict = {"rows": [], "error": None, "snapshot": None}

    seen_op_ids: set[int] = set()
    total_count = 0
    ops_bootstrapped = {"done": False}
    recent_live_op_ids: dict[int, float] = {}

    async def refresh_after_confirm() -> None:
        await load_shelf()
        await load_bin_table()
        await load_assets()

    def _shelf_snapshot(bin_: dict, slots: list[dict]) -> tuple:
        slot_parts = tuple(
            (
                s["id"],
                s.get("status"),
                s.get("quantity"),
                s.get("rfid_tag_epc"),
                s.get("part_number"),
            )
            for s in sorted(slots, key=lambda x: x["id"])
        )
        return (bin_["id"], bin_.get("row_count"), bin_.get("col_count"), slot_parts)

    with ui.row().classes("w-full no-wrap items-stretch").style(
        "min-height: calc(100vh - 52px)"
    ):
        # ── 左栏：上=料盒货柜，下=非标物件 ────────────────────────────────
        with ui.column().classes(
            "w-1/2 min-w-0 border-r border-grey-3 bg-grey-1 flex flex-col overflow-hidden"
        ).style("min-height: calc(100vh - 52px)"):
            with ui.column().classes("w-full flex-1 min-h-0 overflow-y-auto border-b border-grey-3"):
                with ui.row().classes("w-full items-end q-px-md q-pt-sm q-pb-sm gap-3"):
                    ui.label("料盒货柜").classes("text-h6")
                    with ui.row().classes("items-center gap-2 flex-grow justify-end"):
                        shelf_search_input = (
                            ui.input(placeholder="搜索元件、料号、格位")
                            .props("clearable dense outlined prepend-icon=search")
                            .classes("min-w-48 flex-grow max-w-xs")
                        )
                        cabinet_select = ui.select([], label="选择料盒").classes("min-w-40")
                        refresh_shelf_btn = ui.button(icon="refresh").props("flat round dense")

                shelf_hint = ui.label("正在加载…").classes(
                    "text-caption text-grey q-px-md q-mb-sm"
                )

                def _refresh_shelf_view() -> None:
                    shelf_view.refresh()
                    query = shelf_search["query"]
                    slots = shelf_data["slots"]
                    if query and slots:
                        n = count_search_matches(slots, query)
                        shelf_hint.set_text(f"搜索「{query}」· 匹配 {n} / {len(slots)} 个格位")
                    elif shelf_data["bin"] is not None:
                        shelf_hint.set_text(f"共 {len(slots)} 个已配置格位")

                def on_shelf_search() -> None:
                    shelf_search["query"] = (shelf_search_input.value or "").strip()
                    _refresh_shelf_view()

                shelf_search_input.on(
                    "update:model-value", lambda: ui.timer(0.05, on_shelf_search, once=True)
                )

                @ui.refreshable
                def shelf_view() -> None:
                    if shelf_data["error"]:
                        ui.label(f"货架加载失败: {shelf_data['error']}").classes(
                            "q-pa-md text-red"
                        )
                        return
                    if shelf_data["empty"]:
                        ui.label("暂无料盒，请先在「料盒管理」中添加。").classes(
                            "q-pa-md text-grey"
                        )
                        return
                    if shelf_data["bin"] is None:
                        with ui.row().classes("q-pa-md"):
                            ui.spinner(size="lg")
                        return
                    render_shelf_grid(
                        shelf_data["bin"],
                        shelf_data["slots"],
                        compact=True,
                        search=shelf_search["query"],
                    )

                shelf_view()

            with ui.column().classes("w-full flex-shrink-0 overflow-hidden").style(
                "height: 38%; min-height: 200px; max-height: 320px"
            ):
                with ui.row().classes("w-full items-center justify-between q-px-md q-pt-sm q-pb-xs"):
                    ui.label("非标物件").classes("text-h6")
                    refresh_assets_btn = ui.button(icon="refresh").props("flat round dense")

                assets_hint = ui.label("").classes("text-caption text-grey q-px-md q-mb-xs")

                @ui.refreshable
                async def assets_view() -> None:
                    if assets_data["error"]:
                        ui.label(assets_data["error"]).classes("q-px-md text-red")
                        return
                    rows = assets_data["rows"]
                    if not rows:
                        ui.label("暂无非标物件，可在「入库绑定」中登记。").classes(
                            "q-px-md text-grey"
                        )
                        return
                    display_rows = [
                        {
                            **a,
                            "status_label": _ASSET_STATUS_LABELS.get(
                                a.get("status", ""), a.get("status")
                            ),
                        }
                        for a in rows
                    ]
                    columns = [
                        {"name": "asset_code", "label": "编号", "field": "asset_code", "align": "left"},
                        {"name": "name", "label": "名称", "field": "name", "align": "left"},
                        {"name": "status_label", "label": "状态", "field": "status_label"},
                        {"name": "location", "label": "位置", "field": "location"},
                        {"name": "rfid_tag_epc", "label": "EPC", "field": "rfid_tag_epc"},
                    ]
                    ui.table(
                        columns=columns,
                        rows=display_rows,
                        row_key="id",
                        pagination={"rowsPerPage": 5},
                    ).classes("w-full q-px-md").props("dense flat bordered")

                with ui.column().classes("w-full flex-1 min-h-0 overflow-auto"):
                    await assets_view()

        # ── 右栏：状态 / 料盒 / RFID / 快捷入口 ───────────────────────────
        with ui.column().classes("w-1/2 min-w-0 flex flex-col q-pa-md gap-3 overflow-hidden"):
            with ui.row().classes("w-full items-center justify-between"):
                ui.label("料盒实时状态").classes("text-h6")
                status_label = ui.label("● 监听中").classes("text-green text-body2")

            with ui.row().classes("w-full gap-3"):
                with ui.card().classes("flex-1 p-3"):
                    ui.label("料盒数").classes("text-caption text-grey")
                    stat_bins = ui.label("—").classes("text-h5")
                with ui.card().classes("flex-1 p-3"):
                    ui.label("在库格位").classes("text-caption text-grey")
                    stat_occupied = ui.label("—").classes("text-h5 text-green")
                with ui.card().classes("flex-1 p-3"):
                    ui.label("已配置格位").classes("text-caption text-grey")
                    stat_slots = ui.label("—").classes("text-h5")
                with ui.card().classes("flex-1 p-3"):
                    ui.label("出入库操作").classes("text-caption text-grey")
                    event_count = ui.label("0 次").classes("text-h5")

            with ui.card().classes("w-full p-3"):
                ui.label("最近操作").classes("text-caption text-grey")
                latest_operation = ui.label("—").classes(
                    "text-body2 truncate w-full"
                )

            with ui.card().classes("w-full flex-1 min-h-0 flex flex-col p-3"):
                with ui.row().classes("w-full items-center justify-between q-mb-sm"):
                    ui.label("料盒概览").classes("text-subtitle2")
                    refresh_bins_btn = ui.button(icon="refresh").props("flat round dense")

                @ui.refreshable
                def bin_table_view() -> None:
                    if bin_table_data["error"]:
                        ui.label(bin_table_data["error"]).classes("text-red")
                        return
                    if not bin_table_data["rows"]:
                        with ui.row().classes("q-py-md"):
                            ui.spinner(size="md")
                        return
                    columns = [
                        {"name": "code", "label": "编号", "field": "code", "align": "left"},
                        {"name": "name", "label": "名称", "field": "name", "align": "left"},
                        {"name": "status", "label": "状态", "field": "status"},
                        {"name": "location", "label": "位置", "field": "location"},
                    ]
                    ui.table(
                        columns=columns,
                        rows=bin_table_data["rows"],
                        row_key="id",
                        pagination={"rowsPerPage": 5},
                    ).classes("w-full").props("dense flat bordered")

                with ui.column().classes("w-full flex-1 min-h-0 overflow-auto"):
                    bin_table_view()

            with ui.card().classes("w-full flex-1 min-h-0 flex flex-col p-2 gap-1"):
                ui.label("库存操作记录").classes("text-subtitle2 shrink-0")
                event_log = (
                    ui.log(max_lines=100)
                    .classes("w-full flex-1 font-mono text-caption")
                    .style("min-height: 0")
                )

            with ui.row().classes("w-full justify-end"):
                refresh_all_btn = ui.button("刷新全部", icon="sync").props("outline")

    def _update_stats() -> None:
        bins = bin_table_data["rows"]
        slots = shelf_data["slots"]
        stat_bins.set_text(str(len(bins)))
        stat_occupied.set_text(str(sum(1 for s in slots if s.get("status") == "occupied")))
        stat_slots.set_text(str(len(slots)))

    def _format_operation_line(op: dict, ts: str) -> str:
        label = _OPERATION_LABELS.get(op.get("operation", ""), op.get("operation", "?"))
        entity = _ENTITY_LABELS.get(op.get("entity_type", ""), op.get("entity_type", ""))
        if op.get("entity_type") == "asset":
            target = op.get("asset_name") or op.get("asset_code") or "—"
            status = "在库" if op.get("quantity_after") else "借出"
            qty = status
        else:
            target = op.get("slot_code") or "—"
            part = op.get("part_name") or op.get("part_number") or "—"
            target = f"{target} · {part}"
            qty = f"{op.get('quantity_before', '?')}→{op.get('quantity_after', '?')}"
        epc = op.get("epc")
        epc_part = f"  EPC={_short_epc(epc)}" if epc else ""
        entity_part = f"[{entity}] " if entity else ""
        return f"[{ts}] {entity_part}{label} · {target} · {qty}{epc_part}"

    def show_inventory_operation(op: dict, *, ts: str | None = None) -> None:
        nonlocal total_count
        if op.get("status") == "pending":
            return
        if ts is None:
            created = op.get("created_at")
            if isinstance(created, str) and created:
                ts = created[:19].replace("T", " ")
            else:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_count += 1
        line = _format_operation_line(op, ts)
        event_log.push(line)
        latest_operation.set_text(line.split("] ", 1)[-1])
        event_count.set_text(f"{total_count} 次")
        status_label.set_text("● 监听中")
        status_label.classes(remove="text-red", add="text-green")

    async def on_inventory_operation_event(payload: dict) -> None:
        op_id = payload.get("id")
        if op_id is not None:
            recent_live_op_ids[op_id] = time.monotonic()
            seen_op_ids.add(op_id)
        show_inventory_operation(payload)
        await load_shelf()
        await load_bin_table()
        await load_assets()

    hub.on_confirmed("dashboard", refresh_after_confirm)
    hub.on_inventory_operation("dashboard", on_inventory_operation_event)
    ui.context.client.on_disconnect(lambda: hub.off_confirmed("dashboard"))
    ui.context.client.on_disconnect(lambda: hub.off_inventory_operation("dashboard"))

    async def load_shelf() -> None:
        if shelf_loading["active"]:
            return
        shelf_loading["active"] = True
        try:
            try:
                bins = await client.get_bins()
            except Exception as exc:
                shelf_data["bin"] = None
                shelf_data["slots"] = []
                shelf_data["empty"] = False
                shelf_data["error"] = str(exc)
                shelf_data["snapshot"] = None
                shelf_view.refresh()
                shelf_hint.set_text("")
                _update_stats()
                return

            if not bins:
                shelf_data["bin"] = None
                shelf_data["slots"] = []
                shelf_data["empty"] = True
                shelf_data["error"] = None
                shelf_data["snapshot"] = None
                cabinet_select.set_options({})
                shelf_view.refresh()
                shelf_hint.set_text("")
                _update_stats()
                return

            nonlocal cabinet_options
            cabinet_options = {f"{b['code']} · {b['name']}": b["id"] for b in bins}
            cabinet_select.set_options(cabinet_options)
            if cabinet_select.value not in cabinet_options:
                cabinet_select.value = next(iter(cabinet_options))

            cabinet_id = cabinet_options.get(cabinet_select.value)
            if cabinet_id is None:
                return

            bin_ = next((b for b in bins if b["id"] == cabinet_id), None)
            if not bin_:
                return

            try:
                slots = await client.get_slots(cabinet_id=cabinet_id)
            except Exception as exc:
                shelf_data["bin"] = None
                shelf_data["slots"] = []
                shelf_data["empty"] = False
                shelf_data["error"] = str(exc)
                shelf_data["snapshot"] = None
                shelf_view.refresh()
                shelf_hint.set_text("")
                _update_stats()
                return

            shelf_data["bin"] = bin_
            shelf_data["slots"] = slots
            shelf_data["empty"] = False
            shelf_data["error"] = None
            snapshot = _shelf_snapshot(bin_, slots)
            if snapshot != shelf_data["snapshot"]:
                shelf_data["snapshot"] = snapshot
                shelf_view.refresh()
            shelf_hint.set_text(f"共 {len(slots)} 个已配置格位")
            if shelf_search["query"]:
                n = count_search_matches(slots, shelf_search["query"])
                shelf_hint.set_text(
                    f"搜索「{shelf_search['query']}」· 匹配 {n} / {len(slots)} 个格位"
                )
            _update_stats()
        finally:
            shelf_loading["active"] = False

    async def load_bin_table() -> None:
        try:
            bins = await client.get_bins()
        except Exception:
            bin_table_data["rows"] = []
            bin_table_data["error"] = "料盒列表加载失败"
            bin_table_view.refresh()
            _update_stats()
            return
        bin_table_data["rows"] = [
            {**b, "status": bin_status_label(b.get("status"))} for b in bins
        ]
        bin_table_data["error"] = None
        snapshot = tuple(
            (b["id"], b.get("status"), b.get("rfid_tag_epc")) for b in bins
        )
        if snapshot != bin_table_data["snapshot"]:
            bin_table_data["snapshot"] = snapshot
            bin_table_view.refresh()
        _update_stats()

    async def load_assets() -> None:
        try:
            rows = await client.get_assets()
        except Exception:
            assets_data["rows"] = []
            assets_data["error"] = "非标物件加载失败"
            assets_view.refresh()
            return
        assets_data["rows"] = rows
        assets_data["error"] = None
        snapshot = tuple((a["id"], a.get("status"), a.get("rfid_tag_epc")) for a in rows)
        in_stock = sum(1 for a in rows if a.get("status") == "in_stock")
        assets_hint.set_text(f"共 {len(rows)} 件 · 在库 {in_stock}")
        if snapshot != assets_data["snapshot"]:
            assets_data["snapshot"] = snapshot
            assets_view.refresh()

    async def bootstrap_operations() -> None:
        if ops_bootstrapped["done"]:
            return
        try:
            history = await client.get_inventory_operations(limit=30, after_id=0, status="confirmed")
        except Exception as exc:
            status_label.set_text("● 操作记录加载失败")
            status_label.classes(remove="text-green", add="text-red")
            event_log.push(f"[系统] 无法加载库存操作记录: {exc}")
            return
        for op in history:
            seen_op_ids.add(op["id"])
            show_inventory_operation(op)
        ops_bootstrapped["done"] = True

    async def poll_inventory_operations() -> None:
        await bootstrap_operations()
        max_id = max(seen_op_ids) if seen_op_ids else 0
        try:
            operations = await client.get_inventory_operations(limit=50, after_id=max_id)
        except Exception as exc:
            status_label.set_text("● 操作记录 API 异常")
            status_label.classes(remove="text-green", add="text-red")
            event_log.push(f"[系统] 轮询操作记录失败: {exc}")
            return

        need_shelf_refresh = False
        now = time.monotonic()
        for op in operations:
            op_id = op["id"]
            if op_id in seen_op_ids:
                continue
            if now - recent_live_op_ids.get(op_id, 0.0) < 2.0:
                seen_op_ids.add(op_id)
                continue
            seen_op_ids.add(op_id)
            show_inventory_operation(op)
            need_shelf_refresh = True

        if need_shelf_refresh:
            await load_shelf()
            await load_bin_table()
            await load_assets()

    def on_cabinet_change() -> None:
        ui.timer(0.01, load_shelf, once=True)

    cabinet_select.on("update:model-value", on_cabinet_change)
    refresh_shelf_btn.on("click", load_shelf)
    refresh_bins_btn.on("click", load_bin_table)
    refresh_assets_btn.on("click", load_assets)
    refresh_all_btn.on("click", lambda: ui.timer(0.01, initial_load, once=True))

    async def initial_load() -> None:
        await load_shelf()
        await load_bin_table()
        await load_assets()
        await bootstrap_operations()

    ui.timer(0.05, initial_load, once=True)
    ui.timer(2.0, poll_inventory_operations)
    ui.timer(30.0, load_shelf)
