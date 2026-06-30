from __future__ import annotations

import math
from typing import Any

import httpx
from nicegui import ui

from frontend.components import navbar
from frontend.services import ApiClient
from frontend.services.rfid_listener import RfidEventListener

_ASSET_STATUS_LABELS = {
    "in_stock": "在库",
    "checked_out": "已借出",
    "maintenance": "维修中",
}

_ASSET_CATEGORY_LABELS = {
    "tool": "工具",
    "dev_board": "开发板",
    "camera": "相机",
    "other": "其他",
}

_PAGE_SIZE_OPTIONS = {5: "5 条/页", 10: "10 条/页", 20: "20 条/页", 50: "50 条/页"}

_PAGE = "w-full max-w-5xl mx-auto q-px-md q-pb-xl"
_CARD = "w-full rounded-lg shadow-1 border border-grey-3 bg-white"
_SECTION_BODY = "q-px-md q-pb-md"


def _short_epc(epc: str | None, head: int = 10, tail: int = 6) -> str:
    if not epc:
        return "—"
    epc = epc.strip().upper()
    if len(epc) <= head + tail + 1:
        return epc
    return f"{epc[:head]}…{epc[-tail:]}"


def _page_slice(rows: list, page: int, page_size: int) -> tuple[list, int]:
    if not rows:
        return [], 1
    total_pages = max(1, math.ceil(len(rows) / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    return rows[start : start + page_size], total_pages


def _build_tag_entries(items: list[dict], assets: list[dict]) -> list[dict]:
    entries: list[dict] = []
    for row in items:
        epc = row.get("rfid_tag_epc")
        entries.append(
            {
                "id": f"slot-{row['id']}",
                "epc": epc or "",
                "epc_display": _short_epc(epc) if epc else "未绑定",
                "entity_type": "slot_material",
                "entity_label": "料盒物料",
                "record_id": row["id"],
                "target": f"{row.get('part_name')} @ {row.get('slot_code')}",
                "detail": f"{row.get('cabinet_code')} · 数量 {row.get('quantity')}",
                "has_epc": bool(epc),
            }
        )
    for row in assets:
        epc = row.get("rfid_tag_epc")
        entries.append(
            {
                "id": f"asset-{row['id']}",
                "epc": epc or "",
                "epc_display": _short_epc(epc) if epc else "未绑定",
                "entity_type": "asset",
                "entity_label": "非标物件",
                "record_id": row["id"],
                "target": f"{row.get('name')} ({row.get('asset_code')})",
                "detail": f"状态 {_ASSET_STATUS_LABELS.get(row.get('status', ''), row.get('status'))}",
                "has_epc": bool(epc),
            }
        )
    entries.sort(key=lambda e: (not e["has_epc"], e["epc"] or "zzz", e["target"]))
    return entries


def _empty_state(icon: str, text: str) -> None:
    with ui.column().classes("w-full items-center q-py-xl text-grey-6"):
        ui.icon(icon, size="lg")
        ui.label(text).classes("text-body2 q-mt-sm")


def _wire_inventory_row_actions(table, on_edit, on_delete) -> None:
    table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
            <q-btn flat dense no-caps color="primary" icon="edit" label="编辑"
                   @click="$parent.$emit('edit_row', props.row)" />
            <q-btn flat dense no-caps color="negative" icon="delete" label="删除"
                   @click="$parent.$emit('delete_row', props.row)" />
        </q-td>
        """,
    )
    table.on("edit_row", lambda e: on_edit(e.args))
    table.on("delete_row", lambda e: on_delete(e.args))


def _wire_tag_row_actions(table, handlers: dict[str, Any]) -> None:
    table.add_slot(
        "body-cell-bind_status",
        """
        <q-td :props="props">
            <q-badge
                :color="props.value === '已绑定' ? 'positive' : 'grey'"
                :label="props.value"
                outline
            />
        </q-td>
        """,
    )
    table.add_slot(
        "body-cell-entity_label",
        """
        <q-td :props="props">
            <q-badge
                :color="props.row.entity_type === 'slot_material' ? 'blue-grey' : 'teal'"
                :label="props.value"
            />
        </q-td>
        """,
    )
    table.add_slot(
        "body-cell-actions",
        """
        <q-td :props="props">
            <q-btn v-if="!props.row.epc" flat dense no-caps color="primary" icon="link" label="绑定"
                   @click="$parent.$emit('tag_bind', props.row)" />
            <template v-else>
                <q-btn flat dense no-caps icon="swap_horiz" label="换绑"
                       @click="$parent.$emit('tag_rebind', props.row)" />
                <q-btn flat dense no-caps icon="link_off" label="解绑"
                       @click="$parent.$emit('tag_unbind', props.row)" />
            </template>
            <q-btn flat dense no-caps color="negative" icon="delete" label="删除"
                   @click="$parent.$emit('tag_delete', props.row)" />
        </q-td>
        """,
    )
    table.on("tag_bind", lambda e: handlers["bind"](e.args))
    table.on("tag_rebind", lambda e: handlers["rebind"](e.args))
    table.on("tag_unbind", lambda e: handlers["unbind"](e.args))
    table.on("tag_delete", lambda e: handlers["delete"](e.args))


@ui.page("/inventory")
async def inventory_page() -> None:
    navbar()

    with ui.column().classes("w-full bg-grey-1").style("min-height: calc(100vh - 52px)"):
        with ui.column().classes(_PAGE + " gap-4 q-pt-md") as page_main:
            with ui.row().classes("w-full items-start justify-between flex-wrap gap-3"):
                with ui.column().classes("gap-1"):
                    ui.label("库存与标签管理").classes("text-h5 text-weight-medium text-grey-9")
                    ui.label(
                        "查看与编辑库存；向下滚动可管理 RFID 标签绑定。"
                    ).classes("text-body2 text-grey-7")
                with ui.row().classes("gap-2 flex-wrap"):
                    ui.button(
                        "入库绑定",
                        icon="nfc",
                        on_click=lambda: ui.navigate.to("/inventory/register"),
                    ).props("outline color=primary no-caps")
                    ui.button(
                        "操作记录",
                        icon="history",
                        on_click=lambda: ui.navigate.to("/inventory/operations"),
                    ).props("flat color=primary no-caps")

            client = ApiClient()
            data: dict[str, Any] = {
                "slot_rows": [],
                "asset_rows": [],
                "tag_rows": [],
                "slot_page": 1,
                "asset_page": 1,
                "tag_page": 1,
                "page_size": 10,
            }
            rfid_state: dict[str, Any] = {"listening": False, "baseline_id": 0}
            dialog_ctx: dict[str, Any] = {
                "open": False,
                "entity_type": "",
                "record_id": None,
                "action": "",
            }

            stat_slot = ui.label("—").classes("text-h5 text-weight-bold text-primary")
            stat_asset = ui.label("—").classes("text-h5 text-weight-bold text-teal")
            stat_tag = ui.label("—").classes("text-h5 text-weight-bold text-orange")

            with ui.row().classes("w-full gap-3 flex-wrap"):
                for icon, title, el, bg in (
                    ("inventory_2", "料盒物料", stat_slot, "bg-blue-1"),
                    ("category", "非标物件", stat_asset, "bg-teal-1"),
                    ("sell", "已绑定标签", stat_tag, "bg-orange-1"),
                ):
                    with ui.card().classes(f"flex-1 min-w-36 p-3 {_CARD} {bg}"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon(icon, size="sm").classes("text-grey-7")
                            ui.label(title).classes("text-caption text-grey-8")
                        el

            with ui.card().classes(_CARD + " p-3"):
                with ui.row().classes("w-full items-center gap-4 flex-wrap"):
                    low_stock = ui.checkbox("仅显示低库存").props("dense")
                    page_size_select = ui.select(
                        _PAGE_SIZE_OPTIONS,
                        value=10,
                        label="每页条数",
                    ).classes("w-32").props("dense outlined")
                    ui.space()
                    ui.button(
                        "刷新",
                        icon="refresh",
                        on_click=lambda: ui.timer(0.05, load_all, once=True),
                    ).props("outline color=primary no-caps")

    # ── 编辑料盒物料 ─────────────────────────────────────────────
    slot_edit_dialog = ui.dialog()
    slot_edit_refs: dict[str, Any] = {}
    slot_edit_ctx: dict[str, Any] = {"id": None}

    with slot_edit_dialog, ui.card().classes("p-5 w-full rounded-lg").style(
        "min-width: 360px; max-width: 480px"
    ):
        with ui.row().classes("items-center gap-2 q-mb-md"):
            ui.icon("inventory_2", size="sm").classes("text-primary")
            ui.label("编辑料盒物料").classes("text-h6")
        slot_edit_refs["quantity"] = ui.number("数量", value=0, min=0).classes("w-full").props("outlined dense")
        slot_edit_refs["min_stock"] = ui.number("最低库存", value=0, min=0).classes("w-full").props("outlined dense")
        slot_edit_refs["max_stock"] = ui.number("最高库存", value=0, min=0).classes("w-full").props("outlined dense")
        slot_edit_refs["reorder_point"] = ui.number("补货点", value=0, min=0).classes("w-full").props("outlined dense")
        slot_edit_refs["batch_no"] = ui.input("批次号").classes("w-full").props("outlined dense")
        slot_edit_refs["note"] = ui.input("修改备注（可选）").classes("w-full").props("outlined dense")

        async def save_slot_edit() -> None:
            item_id = slot_edit_ctx["id"]
            if item_id is None:
                return
            payload = {
                "quantity": int(slot_edit_refs["quantity"].value or 0),
                "min_stock": int(slot_edit_refs["min_stock"].value or 0),
                "max_stock": int(slot_edit_refs["max_stock"].value or 0),
                "reorder_point": int(slot_edit_refs["reorder_point"].value or 0),
                "batch_no": (slot_edit_refs["batch_no"].value or "").strip() or None,
                "note": (slot_edit_refs["note"].value or "").strip() or None,
            }
            try:
                await client.update_inventory_item(item_id, payload)
                ui.notify("已保存并记入操作记录", type="positive")
                slot_edit_dialog.close()
                await load_all()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                try:
                    detail = exc.response.json().get("detail", detail)
                except Exception:
                    pass
                ui.notify(f"保存失败: {detail}", type="negative")

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("取消", on_click=slot_edit_dialog.close).props("flat")
            ui.button("保存", icon="save", on_click=save_slot_edit).props("color=primary")

    def open_slot_edit(row: dict) -> None:
        slot_edit_ctx["id"] = row["id"]
        slot_edit_refs["quantity"].value = row.get("quantity", 0)
        slot_edit_refs["min_stock"].value = row.get("min_stock", 0)
        slot_edit_refs["max_stock"].value = row.get("max_stock") or 0
        slot_edit_refs["reorder_point"].value = row.get("reorder_point") or 0
        slot_edit_refs["batch_no"].value = row.get("batch_no") or ""
        slot_edit_refs["note"].value = ""
        slot_edit_dialog.open()

    # ── 编辑非标物件 ─────────────────────────────────────────────
    asset_edit_dialog = ui.dialog()
    asset_edit_refs: dict[str, Any] = {}
    asset_edit_ctx: dict[str, Any] = {"id": None}

    with asset_edit_dialog, ui.card().classes("p-5 w-full rounded-lg").style(
        "min-width: 360px; max-width: 480px"
    ):
        with ui.row().classes("items-center gap-2 q-mb-md"):
            ui.icon("category", size="sm").classes("text-primary")
            ui.label("编辑非标物件").classes("text-h6")
        asset_edit_refs["name"] = ui.input("名称").classes("w-full").props("outlined dense")
        asset_edit_refs["category"] = ui.select(
            _ASSET_CATEGORY_LABELS, label="类别"
        ).classes("w-full").props("outlined dense")
        asset_edit_refs["serial_no"] = ui.input("序列号").classes("w-full").props("outlined dense")
        asset_edit_refs["location"] = ui.input("位置").classes("w-full").props("outlined dense")
        asset_edit_refs["remark"] = ui.input("备注").classes("w-full").props("outlined dense")
        asset_edit_refs["note"] = ui.input("修改备注（可选）").classes("w-full").props("outlined dense")

        async def save_asset_edit() -> None:
            asset_id = asset_edit_ctx["id"]
            if asset_id is None:
                return
            payload = {
                "name": (asset_edit_refs["name"].value or "").strip(),
                "category": asset_edit_refs["category"].value,
                "serial_no": (asset_edit_refs["serial_no"].value or "").strip() or None,
                "location": (asset_edit_refs["location"].value or "").strip() or None,
                "remark": (asset_edit_refs["remark"].value or "").strip() or None,
                "note": (asset_edit_refs["note"].value or "").strip() or None,
            }
            try:
                await client.update_asset_record(asset_id, payload)
                ui.notify("已保存并记入操作记录", type="positive")
                asset_edit_dialog.close()
                await load_all()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                try:
                    detail = exc.response.json().get("detail", detail)
                except Exception:
                    pass
                ui.notify(f"保存失败: {detail}", type="negative")

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("取消", on_click=asset_edit_dialog.close).props("flat")
            ui.button("保存", icon="save", on_click=save_asset_edit).props("color=primary")

    def open_asset_edit(row: dict) -> None:
        asset_edit_ctx["id"] = row["id"]
        asset_edit_refs["name"].value = row.get("name") or ""
        asset_edit_refs["category"].value = row.get("category") or "other"
        asset_edit_refs["serial_no"].value = row.get("serial_no") or ""
        asset_edit_refs["location"].value = row.get("location") or ""
        asset_edit_refs["remark"].value = row.get("remark") or ""
        asset_edit_refs["note"].value = ""
        asset_edit_dialog.open()

    # ── 标签操作对话框 ─────────────────────────────────────────────
    tag_action_dialog = ui.dialog()
    tag_action_dialog.on("hide", lambda: dialog_ctx.update(open=False))
    tag_dialog_refs: dict[str, Any] = {}

    with tag_action_dialog, ui.card().classes("p-5 w-full rounded-lg").style(
        "min-width: 360px; max-width: 480px"
    ):
        tag_dialog_refs["title"] = ui.label("").classes("text-h6")
        tag_dialog_refs["hint"] = ui.label("").classes("text-body2 text-grey q-mb-sm")
        tag_dialog_refs["epc"] = ui.input("RFID EPC").classes("w-full").props("outlined dense")
        tag_dialog_refs["listen"] = ui.label("").classes("text-caption text-grey q-mb-sm")

        async def start_tag_listen() -> None:
            try:
                events = await client.get_rfid_events(limit=200, after_id=0)
                rfid_state["baseline_id"] = max((e["id"] for e in events), default=0)
            except Exception:
                rfid_state["baseline_id"] = 0
            rfid_state["listening"] = True
            tag_dialog_refs["listen"].set_text("● 请将标签靠近读卡器…")
            tag_dialog_refs["listen"].classes(remove="text-green", add="text-blue")

        async def submit_tag_action() -> None:
            entity_type = dialog_ctx["entity_type"]
            record_id = dialog_ctx["record_id"]
            action = dialog_ctx["action"]
            if record_id is None:
                return
            try:
                if action == "unbind":
                    await client.unbind_inventory_tag(
                        {"entity_type": entity_type, "record_id": record_id}
                    )
                    ui.notify("已解绑标签", type="positive")
                elif action in ("bind", "rebind"):
                    epc = (tag_dialog_refs["epc"].value or "").strip().upper()
                    if not epc:
                        ui.notify("请输入或读取 EPC", type="warning")
                        return
                    payload = {
                        "entity_type": entity_type,
                        "record_id": record_id,
                        "rfid_tag_epc": epc,
                    }
                    if action == "bind":
                        await client.bind_inventory_tag(payload)
                        ui.notify("已绑定标签", type="positive")
                    else:
                        await client.rebind_inventory_tag(payload)
                        ui.notify("已换绑标签", type="positive")
                tag_action_dialog.close()
                await load_all()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                try:
                    detail = exc.response.json().get("detail", detail)
                except Exception:
                    pass
                ui.notify(f"操作失败: {detail}", type="negative")

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("取消", on_click=tag_action_dialog.close).props("flat")
            ui.button("读卡", icon="nfc", on_click=start_tag_listen).props("outline")
            ui.button("确认", on_click=submit_tag_action).props("color=primary")

    delete_dialog = ui.dialog()
    delete_ctx: dict[str, Any] = {}

    with delete_dialog, ui.card().classes("p-5 rounded-lg").style("min-width: 320px"):
        with ui.row().classes("items-center gap-2 q-mb-sm"):
            ui.icon("warning", color="orange").classes("text-orange")
            ui.label("确认删除").classes("text-h6")
        delete_body = ui.label("").classes("text-body2 q-mb-md")

        async def confirm_delete() -> None:
            try:
                await client.delete_inventory_record(
                    delete_ctx["entity_type"], delete_ctx["record_id"]
                )
                ui.notify("已删除", type="positive")
                delete_dialog.close()
                await load_all()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                try:
                    detail = exc.response.json().get("detail", detail)
                except Exception:
                    pass
                ui.notify(f"删除失败: {detail}", type="negative")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("取消", on_click=delete_dialog.close).props("flat")
            ui.button("删除", on_click=confirm_delete).props("color=negative")

    def open_tag_action(
        *,
        entity_type: str,
        record_id: int,
        action: str,
        name: str,
        current_epc: str | None,
    ) -> None:
        dialog_ctx.update(
            entity_type=entity_type,
            record_id=record_id,
            action=action,
            open=True,
        )
        titles = {"bind": "绑定标签", "rebind": "换绑标签", "unbind": "解绑标签"}
        tag_dialog_refs["title"].set_text(titles.get(action, action))
        if action == "unbind":
            tag_dialog_refs["hint"].set_text(
                f"确认解绑「{name}」的标签 {_short_epc(current_epc)}？库存记录将保留。"
            )
            tag_dialog_refs["epc"].set_visibility(False)
        else:
            tag_dialog_refs["hint"].set_text(
                f"为「{name}」{'绑定' if action == 'bind' else '换绑'}新标签"
                + (f"（当前 {_short_epc(current_epc)}）" if current_epc else "")
            )
            tag_dialog_refs["epc"].set_visibility(True)
            tag_dialog_refs["epc"].value = ""
        tag_dialog_refs["listen"].set_text("")
        tag_action_dialog.open()

    def open_delete(*, entity_type: str, record_id: int, name: str) -> None:
        delete_ctx.update(entity_type=entity_type, record_id=record_id)
        delete_body.set_text(f"确定删除「{name}」？此操作不可撤销。")
        delete_dialog.open()

    async def on_live_rfid(payload: dict) -> None:
        if not rfid_state["listening"] or not dialog_ctx.get("open"):
            return
        epc = (payload.get("epc") or "").strip()
        if epc:
            tag_dialog_refs["epc"].value = epc.upper()
            rfid_state["listening"] = False
            tag_dialog_refs["listen"].set_text(f"● 已读取 {_short_epc(epc)}")
            tag_dialog_refs["listen"].classes(remove="text-blue", add="text-green")

    RfidEventListener(on_live_rfid).start()

    async def poll_rfid() -> None:
        if not rfid_state["listening"] or not dialog_ctx.get("open"):
            return
        try:
            events = await client.get_rfid_events(limit=30, after_id=rfid_state["baseline_id"])
        except Exception:
            return
        for event in events:
            eid = event["id"]
            if eid <= rfid_state["baseline_id"]:
                continue
            epc = (event.get("epc") or "").strip()
            if epc:
                rfid_state["baseline_id"] = eid
                tag_dialog_refs["epc"].value = epc.upper()
                rfid_state["listening"] = False
                tag_dialog_refs["listen"].set_text(f"● 已读取 {_short_epc(epc)}")
                tag_dialog_refs["listen"].classes(remove="text-blue", add="text-green")
                return

    def render_pager(
        *,
        page_key: str,
        rows: list,
        label_el,
    ) -> list:
        page_size = int(page_size_select.value or data["page_size"])
        page = data[page_key]
        chunk, total_pages = _page_slice(rows, page, page_size)
        if page > total_pages:
            page = total_pages
            data[page_key] = page
            chunk, _ = _page_slice(rows, page, page_size)
        label_el.set_text(f"第 {page} / {total_pages} 页 · 共 {len(rows)} 条")
        return chunk

    def render_slot_section() -> None:
        chunk = render_pager(
            page_key="slot_page",
            rows=data["slot_rows"],
            label_el=slot_pager_label,
        )
        slot_list.clear()
        with slot_list:
            if not data["slot_rows"]:
                _empty_state("inventory_2", "暂无料盒物料库存")
                return
            display = [
                {
                    **row,
                    "stock_hint": (
                        "低库存"
                        if row.get("quantity", 0) <= row.get("min_stock", 0)
                        else ""
                    ),
                }
                for row in chunk
            ]
            columns = [
                {"name": "part_number", "label": "料号", "field": "part_number", "align": "left"},
                {"name": "part_name", "label": "名称", "field": "part_name", "align": "left"},
                {"name": "cabinet_code", "label": "料盒", "field": "cabinet_code"},
                {"name": "slot_code", "label": "格位", "field": "slot_code"},
                {"name": "quantity", "label": "数量", "field": "quantity", "align": "right"},
                {"name": "available_qty", "label": "可用", "field": "available_qty", "align": "right"},
                {"name": "min_stock", "label": "最低", "field": "min_stock", "align": "right"},
                {"name": "stock_hint", "label": "", "field": "stock_hint"},
                {"name": "actions", "label": "操作", "field": "actions", "align": "center"},
            ]
            table = ui.table(
                columns=columns,
                rows=display,
                row_key="id",
                pagination={"rowsPerPage": 0},
            ).classes("w-full").props("dense flat bordered separator=horizontal")
            table.add_slot(
                "body-cell-stock_hint",
                """
                <q-td :props="props">
                    <q-badge v-if="props.value" color="orange" outline :label="props.value" />
                </q-td>
                """,
            )
            _wire_inventory_row_actions(
                table,
                open_slot_edit,
                lambda row: open_delete(
                    entity_type="slot_material",
                    record_id=row["id"],
                    name=f"{row.get('part_name')} @ {row.get('slot_code')}",
                ),
            )

    def render_asset_section() -> None:
        chunk = render_pager(
            page_key="asset_page",
            rows=data["asset_rows"],
            label_el=asset_pager_label,
        )
        asset_list.clear()
        with asset_list:
            if not data["asset_rows"]:
                _empty_state("category", "暂无非标物件")
                return
            display = [
                {
                    **a,
                    "status_label": _ASSET_STATUS_LABELS.get(a.get("status", ""), a.get("status")),
                    "category_label": _ASSET_CATEGORY_LABELS.get(
                        a.get("category", ""), a.get("category")
                    ),
                    "epc_short": _short_epc(a.get("rfid_tag_epc")),
                }
                for a in chunk
            ]
            columns = [
                {"name": "asset_code", "label": "编号", "field": "asset_code", "align": "left"},
                {"name": "name", "label": "名称", "field": "name", "align": "left"},
                {"name": "category_label", "label": "类别", "field": "category_label"},
                {"name": "status_label", "label": "状态", "field": "status_label"},
                {"name": "location", "label": "位置", "field": "location"},
                {"name": "epc_short", "label": "EPC", "field": "epc_short", "align": "left"},
                {"name": "actions", "label": "操作", "field": "actions", "align": "center"},
            ]
            table = ui.table(
                columns=columns,
                rows=display,
                row_key="id",
                pagination={"rowsPerPage": 0},
            ).classes("w-full").props("dense flat bordered separator=horizontal")
            table.add_slot(
                "body-cell-status_label",
                """
                <q-td :props="props">
                    <q-badge
                        :color="props.value === '在库' ? 'green' : props.value === '已借出' ? 'blue' : 'grey'"
                        :label="props.value"
                        outline
                    />
                </q-td>
                """,
            )
            _wire_inventory_row_actions(
                table,
                open_asset_edit,
                lambda row: open_delete(
                    entity_type="asset",
                    record_id=row["id"],
                    name=f"{row.get('name')} ({row.get('asset_code')})",
                ),
            )

    def render_tag_section() -> None:
        chunk = render_pager(
            page_key="tag_page",
            rows=data["tag_rows"],
            label_el=tag_pager_label,
        )
        tag_list.clear()
        with tag_list:
            if not data["tag_rows"]:
                _empty_state("sell", "暂无标签条目")
                return
            display = [
                {
                    **entry,
                    "bind_status": "已绑定" if entry.get("has_epc") else "未绑定",
                }
                for entry in chunk
            ]
            columns = [
                {"name": "epc_display", "label": "EPC", "field": "epc_display", "align": "left"},
                {"name": "bind_status", "label": "状态", "field": "bind_status"},
                {"name": "entity_label", "label": "类型", "field": "entity_label"},
                {"name": "target", "label": "绑定对象", "field": "target", "align": "left"},
                {"name": "detail", "label": "详情", "field": "detail", "align": "left"},
                {"name": "actions", "label": "操作", "field": "actions", "align": "center"},
            ]
            table = ui.table(
                columns=columns,
                rows=display,
                row_key="id",
                pagination={"rowsPerPage": 0},
            ).classes("w-full").props("dense flat bordered separator=horizontal")
            _wire_tag_row_actions(
                table,
                {
                    "bind": lambda row: open_tag_action(
                        entity_type=row["entity_type"],
                        record_id=row["record_id"],
                        action="bind",
                        name=row["target"],
                        current_epc=None,
                    ),
                    "rebind": lambda row: open_tag_action(
                        entity_type=row["entity_type"],
                        record_id=row["record_id"],
                        action="rebind",
                        name=row["target"],
                        current_epc=row["epc"],
                    ),
                    "unbind": lambda row: open_tag_action(
                        entity_type=row["entity_type"],
                        record_id=row["record_id"],
                        action="unbind",
                        name=row["target"],
                        current_epc=row["epc"],
                    ),
                    "delete": lambda row: open_delete(
                        entity_type=row["entity_type"],
                        record_id=row["record_id"],
                        name=row["target"],
                    ),
                },
            )

    @ui.refreshable
    def slot_section() -> None:
        render_slot_section()

    @ui.refreshable
    def asset_section() -> None:
        render_asset_section()

    @ui.refreshable
    def tag_section() -> None:
        render_tag_section()

    def change_page(page_key: str, delta: int, refresh) -> None:
        page_size = int(page_size_select.value or data["page_size"])
        rows_key = {
            "slot_page": "slot_rows",
            "asset_page": "asset_rows",
            "tag_page": "tag_rows",
        }[page_key]
        total_pages = max(1, math.ceil(len(data[rows_key]) / page_size))
        data[page_key] = max(1, min(data[page_key] + delta, total_pages))
        refresh.refresh()

    async def load_all() -> None:
        try:
            data["slot_rows"] = await client.get_inventory(low_stock_only=low_stock.value)
            assets = await client.get_assets()
            data["asset_rows"] = assets
            data["tag_rows"] = _build_tag_entries(data["slot_rows"], assets)
        except httpx.HTTPError as exc:
            ui.notify(f"加载失败: {exc}", type="negative")
            return
        stat_slot.set_text(str(len(data["slot_rows"])))
        stat_asset.set_text(str(len(data["asset_rows"])))
        bound = sum(1 for t in data["tag_rows"] if t.get("has_epc"))
        stat_tag.set_text(str(bound))
        slot_section.refresh()
        asset_section.refresh()
        tag_section.refresh()

    def on_page_size_change() -> None:
        data["page_size"] = int(page_size_select.value or 10)
        data["slot_page"] = 1
        data["asset_page"] = 1
        data["tag_page"] = 1
        slot_section.refresh()
        asset_section.refresh()
        tag_section.refresh()

    def pagination_row(page_key: str, label_el, refresh_fn) -> None:
        with ui.row().classes("w-full items-center justify-center gap-1 q-pt-2"):
            ui.button(
                icon="chevron_left",
                on_click=lambda: change_page(page_key, -1, refresh_fn),
            ).props("flat dense round")
            label_el.classes("text-caption text-grey-8 q-px-sm")
            ui.button(
                icon="chevron_right",
                on_click=lambda: change_page(page_key, 1, refresh_fn),
            ).props("flat dense round")

    with page_main:
        slot_pager_label = ui.label("")
        asset_pager_label = ui.label("")
        tag_pager_label = ui.label("")

        slot_list = ui.column().classes("w-full")
        asset_list = ui.column().classes("w-full")
        tag_list = ui.column().classes("w-full")

        with ui.card().classes(_CARD + " overflow-hidden"):
            with ui.expansion(
                "料盒物料",
                icon="inventory_2",
                value=True,
            ).classes("w-full").props("dense header-class=text-weight-medium"):
                with ui.column().classes(_SECTION_BODY):
                    slot_list
                    slot_section()
                    pagination_row("slot_page", slot_pager_label, slot_section)

        with ui.card().classes(_CARD + " overflow-hidden"):
            with ui.expansion(
                "非标物件",
                icon="category",
                value=True,
            ).classes("w-full").props("dense header-class=text-weight-medium"):
                with ui.column().classes(_SECTION_BODY):
                    asset_list
                    asset_section()
                    pagination_row("asset_page", asset_pager_label, asset_section)

        with ui.card().classes(_CARD + " overflow-hidden"):
            with ui.expansion(
                "标签管理",
                icon="sell",
                value=False,
            ).classes("w-full").props("dense header-class=text-weight-medium"):
                ui.label("以 RFID 标签为主条目，可绑定、换绑或解绑。").classes(
                    "text-caption text-grey-7 q-px-md q-pt-sm"
                )
                with ui.column().classes(_SECTION_BODY):
                    tag_list
                    tag_section()
                    pagination_row("tag_page", tag_pager_label, tag_section)

        page_size_select.on(
            "update:model-value", lambda: ui.timer(0.05, on_page_size_change, once=True)
        )
        low_stock.on("update:model-value", lambda: ui.timer(0.05, load_all, once=True))

        ui.timer(0.05, load_all, once=True)
        ui.timer(1.0, poll_rfid)


@ui.page("/inventory/manage")
async def inventory_manage_redirect() -> None:
    ui.navigate.to("/inventory")
