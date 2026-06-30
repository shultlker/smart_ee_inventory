from __future__ import annotations

from nicegui import ui

from frontend.components import navbar
from frontend.components.presence_confirm import mount_presence_confirm_dialog
from frontend.services import ApiClient

_OPERATION_LABELS = {
    "take_out": "出库",
    "return": "归还",
    "register_in": "入库绑定",
    "tag_bind": "绑定标签",
    "tag_rebind": "换绑标签",
    "tag_unbind": "解绑标签",
    "delete": "删除库存",
    "manual_edit": "手动修改",
}
_STATUS_LABELS = {
    "pending": "待确认",
    "confirmed": "已确认",
    "cancelled": "已取消",
}
_ENTITY_LABELS = {
    "slot_material": "料盒物料",
    "asset": "非标物件",
}


@ui.page("/inventory/operations")
async def inventory_operations_page() -> None:
    navbar()
    ui.label("库存操作记录").classes("text-h5 q-pa-md")

    client = ApiClient()
    filter_status = ui.select(
        {
            "": "全部状态",
            "pending": "待确认",
            "confirmed": "已确认",
            "cancelled": "已取消",
        },
        value="",
        label="状态",
    ).classes("q-px-md min-w-40")
    filter_operation = ui.select(
        {
            "": "全部类型",
            "take_out": "出库",
            "return": "归还",
            "register_in": "入库绑定",
            "manual_edit": "手动修改",
            "tag_bind": "绑定标签",
            "tag_rebind": "换绑",
            "tag_unbind": "解绑",
            "delete": "删除",
        },
        value="",
        label="操作类型",
    ).classes("q-px-md min-w-40")

    @ui.refreshable
    async def table_view() -> None:
        params_status = filter_status.value or None
        params_op = filter_operation.value or None
        try:
            rows = await client.get_inventory_operations(
                limit=200,
                status=params_status,
                operation=params_op,
            )
        except Exception as exc:
            ui.label(f"加载失败: {exc}").classes("text-red q-pa-md")
            return

        display_rows = []
        for r in rows:
            target = r.get("slot_code") or r.get("asset_name") or "—"
            if r.get("part_name"):
                target = f"{target} · {r['part_name']}"
            extra = ""
            if r.get("user_name"):
                extra = f"{r['user_name']} / {r.get('project_name') or '—'}"
            elif r.get("consumed_qty"):
                extra = f"消耗 {r['consumed_qty']}"
            display_rows.append(
                {
                    **r,
                    "operation_label": _OPERATION_LABELS.get(
                        r.get("operation", ""), r.get("operation")
                    ),
                    "status_label": _STATUS_LABELS.get(r.get("status", ""), r.get("status")),
                    "entity_label": _ENTITY_LABELS.get(
                        r.get("entity_type", ""), r.get("entity_type")
                    ),
                    "target_label": target,
                    "extra_label": extra,
                    "qty_label": f"{r.get('quantity_before', '?')}→{r.get('quantity_after', '?')}",
                    "created_label": (r.get("created_at") or "")[:19].replace("T", " "),
                }
            )

        columns = [
            {"name": "id", "label": "ID", "field": "id", "align": "left"},
            {"name": "created_label", "label": "时间", "field": "created_label", "align": "left"},
            {"name": "status_label", "label": "状态", "field": "status_label"},
            {"name": "operation_label", "label": "操作", "field": "operation_label"},
            {"name": "entity_label", "label": "类型", "field": "entity_label"},
            {"name": "target_label", "label": "对象", "field": "target_label", "align": "left"},
            {"name": "qty_label", "label": "数量变化", "field": "qty_label"},
            {"name": "extra_label", "label": "使用人/消耗", "field": "extra_label", "align": "left"},
            {"name": "epc", "label": "EPC", "field": "epc"},
            {"name": "note", "label": "备注", "field": "note", "align": "left"},
        ]
        table = ui.table(
            columns=columns,
            rows=display_rows,
            row_key="id",
            pagination={"rowsPerPage": 15},
        )
        table.classes("w-full q-px-md")

        def on_row_click(e) -> None:
            row = e.args[1]
            if row.get("status") != "pending":
                return
            confirm_state["open_for_operation"](row)

        table.on("rowClick", on_row_click)

        pending = [r for r in display_rows if r.get("status") == "pending"]
        if pending:
            ui.label(f"待确认 {len(pending)} 条 — 点击行可处理").classes(
                "text-caption text-orange q-px-md q-mt-sm"
            )

    def refresh() -> None:
        table_view.refresh()

    confirm_state = mount_presence_confirm_dialog(client, on_confirmed=refresh)

    clear_dialog = ui.dialog()

    with clear_dialog, ui.card().classes("p-4 w-80"):
        ui.label("清空操作记录").classes("text-h6")
        ui.label("将删除全部出入库操作记录，并恢复待确认格位状态。此操作不可撤销。").classes(
            "text-body2 text-grey q-my-md"
        )

        async def do_clear() -> None:
            try:
                result = await client.clear_inventory_operations()
            except Exception as exc:
                ui.notify(f"清空失败: {exc}", type="negative")
                return
            clear_dialog.close()
            confirm_state["prompted_ids"].clear()
            ui.notify(f"已清空 {result.get('deleted', 0)} 条记录", type="positive")
            refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("取消", on_click=clear_dialog.close).props("flat")
            ui.button("确认清空", on_click=do_clear).props("color=negative")

    await table_view()

    with ui.row().classes("q-ma-md gap-2"):
        ui.button("刷新", on_click=refresh)
        ui.button("清空记录", icon="delete_sweep", on_click=clear_dialog.open).props("outline color=negative")
        filter_status.on("update:model-value", lambda: refresh())
        filter_operation.on("update:model-value", lambda: refresh())

    async def load_pending() -> None:
        try:
            pending = await client.get_inventory_operations(limit=20, status="pending")
        except Exception:
            return
        for op in pending:
            confirm_state["open_for_operation"](op)
            break

    ui.timer(0.2, load_pending, once=True)
