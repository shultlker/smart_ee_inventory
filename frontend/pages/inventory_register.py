from __future__ import annotations

import httpx
from collections import Counter
from nicegui import ui

from frontend.components import navbar
from frontend.services import ApiClient
from frontend.services.rfid_listener import RfidEventListener


def _short_epc(epc: str, head: int = 12, tail: int = 6) -> str:
    epc = epc.strip().upper()
    if len(epc) <= head + tail + 1:
        return epc
    return f"{epc[:head]}…{epc[-tail:]}"


@ui.page("/inventory/register")
async def inventory_register_page(epc: str = "", rssi: str = "", bind_type: str = "") -> None:
    prefilled_epc = (epc or "").strip().upper()
    prefilled_bind = (bind_type or "slot_material").strip().lower()
    if prefilled_bind not in ("slot_material", "asset"):
        prefilled_bind = "slot_material"
    prefilled_rssi: int | None = None
    if rssi:
        try:
            prefilled_rssi = int(rssi)
        except ValueError:
            prefilled_rssi = None

    navbar()
    ui.label("新建库存 · RFID 绑定").classes("text-h5 q-pa-md")

    client = ApiClient()
    refs: dict = {}
    ctx: dict = {
        "bin_options": {},
        "part_options": {},
        "part_meta": {},
        "slot_id_map": {},
        "category_options": {},
    }
    state: dict = {
        "listening": False,
        "baseline_id": 0,
        "poll_count": 0,
        "captured_epc": "",
    }

    gateway_status = ui.label("RFID 状态加载中…").classes("q-ma-md text-caption text-grey")
    load_hint = ui.label("正在加载料盒与物料列表…").classes("q-px-md text-caption text-grey")

    async def fetch_latest_event_id() -> int:
        try:
            events = await client.get_rfid_events(limit=200, after_id=0)
        except Exception:
            return 0
        return max((e["id"] for e in events), default=0)

    def apply_epc_to_form(epc: str, rssi: int | None) -> None:
        epc = epc.strip().upper()
        state["captured_epc"] = epc
        if "epc_display" in refs:
            refs["epc_display"].value = epc
        if "manual_epc" in refs:
            refs["manual_epc"].value = epc
        if "epc_label" in refs:
            refs["epc_label"].set_text(f"已捕获: {_short_epc(epc)}")
            refs["epc_label"].classes(remove="text-grey", add="text-green")
        rssi_str = f"{rssi} dBm" if rssi is not None else "N/A"
        if "rssi_label" in refs:
            refs["rssi_label"].set_text(f"RSSI: {rssi_str}")
        if "listen_status" in refs:
            refs["listen_status"].set_text(f"● 已选定标签（{rssi_str}），请填写信息后入库")
            refs["listen_status"].classes(remove="text-blue text-grey", add="text-green")
        if "poll_hint" in refs:
            refs["poll_hint"].set_text("")

    def capture_tag(epc: str, rssi: int | None) -> None:
        epc = epc.strip().upper()
        state["listening"] = False
        apply_epc_to_form(epc, rssi)
        ui.notify(f"已读取标签: {_short_epc(epc)}", type="positive")

    async def on_live_rfid(payload: dict) -> None:
        if not state["listening"]:
            return
        epc = (payload.get("epc") or "").strip()
        if not epc:
            return
        capture_tag(epc, payload.get("rssi"))

    RfidEventListener(on_live_rfid).start()

    async def poll_rfid() -> None:
        """HTTP fallback if an in-process event was missed."""
        if not state["listening"] or "listen_status" not in refs:
            return
        try:
            events = await client.get_rfid_events(limit=50, after_id=state["baseline_id"])
        except Exception:
            refs["listen_status"].set_text("● API 异常，监听已停止")
            refs["listen_status"].classes(remove="text-blue", add="text-red")
            state["listening"] = False
            return
        for event in events:
            eid = event["id"]
            if eid <= state["baseline_id"]:
                continue
            epc = (event.get("epc") or "").strip()
            if not epc:
                state["baseline_id"] = max(state["baseline_id"], eid)
                continue
            state["baseline_id"] = eid
            capture_tag(epc, event.get("rssi"))
            return

    part_dialog = ui.dialog()
    part_form: dict[str, ui.element] = {}

    def _part_label(c: dict, *, disambiguate: bool = False) -> str:
        name = (c.get("name") or "").strip() or (c.get("part_number") or "").strip() or "—"
        if disambiguate:
            part_number = (c.get("part_number") or "").strip()
            if part_number and part_number != name:
                return f"{name} · {part_number}"
        return name

    def apply_component_options(components: list[dict], *, select_id: int | None = None) -> None:
        ctx["part_options"] = {}
        ctx["part_meta"] = {}
        base_labels = [_part_label(c) for c in components]
        duplicate_names = {lb for lb, n in Counter(base_labels).items() if n > 1}
        for c in components:
            base = _part_label(c)
            label = _part_label(c, disambiguate=base in duplicate_names)
            ctx["part_options"][c["id"]] = label
            ctx["part_meta"][c["id"]] = c
        part_select.set_options(ctx["part_options"])
        if select_id is not None and select_id in ctx["part_meta"]:
            part_select.value = select_id
        elif ctx["part_options"]:
            part_select.value = next(iter(ctx["part_options"]))
        else:
            part_select.value = None
        refresh_part_detail()

    with part_dialog, ui.card().classes("p-4 w-96"):
        ui.label("新建元件").classes("text-h6")
        part_form["part_number"] = ui.input("料号 *").classes("w-full")
        part_form["name"] = ui.input("名称 *").classes("w-full")
        part_form["category"] = ui.select({}, label="分类（可选）").classes("w-full")
        part_form["package"] = ui.input("封装").classes("w-full")
        part_form["value"] = ui.input("规格/阻值").classes("w-full")
        part_form["manufacturer"] = ui.input("制造商").classes("w-full")

        async def save_new_part() -> None:
            part_number = (part_form["part_number"].value or "").strip()
            name = (part_form["name"].value or "").strip()
            if not part_number or not name:
                ui.notify("请填写料号与名称", type="warning")
                return
            payload: dict = {
                "part_number": part_number,
                "name": name,
                "package": (part_form["package"].value or "").strip() or None,
                "value": (part_form["value"].value or "").strip() or None,
                "manufacturer": (part_form["manufacturer"].value or "").strip() or None,
            }
            category_id = part_form["category"].value
            if category_id is not None:
                payload["category_id"] = category_id
            try:
                created = await client.create_component(payload)
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                try:
                    detail = exc.response.json().get("detail", detail)
                except Exception:
                    pass
                ui.notify(f"创建失败: {detail}", type="negative")
                return
            except Exception as exc:
                ui.notify(f"创建失败: {exc}", type="negative")
                return
            components = await client.get_components()
            apply_component_options(components, select_id=created["id"])
            part_dialog.close()
            ui.notify(f"已创建元件: {created['part_number']}", type="positive")
            part_form["part_number"].value = ""
            part_form["name"].value = ""
            part_form["package"].value = ""
            part_form["value"].value = ""
            part_form["manufacturer"].value = ""
            if ctx["category_options"]:
                part_form["category"].value = next(iter(ctx["category_options"]))

        with ui.row().classes("w-full justify-end gap-2 q-mt-md"):
            ui.button("取消", on_click=part_dialog.close).props("flat")
            ui.button("保存", on_click=save_new_part).props("color=primary")

    with ui.card().classes("q-ma-md p-4 w-full max-w-3xl"):
        ui.label("绑定类型").classes("text-subtitle1 q-mb-sm")
        bind_type_select = ui.radio(
            {"slot_material": "料盒物料（格位库存）", "asset": "非标物件（工具/设备等）"},
            value=prefilled_bind,
        ).props("inline")

        slot_panel = ui.column().classes("w-full")
        asset_panel = ui.column().classes("w-full")

        with slot_panel:
            ui.label("料盒与格位").classes("text-subtitle1 q-mb-sm")
            cabinet_select = ui.select([], label="料盒").classes("w-full")
            slot_mode = ui.radio(
                {"position": "指定行列", "existing": "选择已有空位"},
                value="position",
            ).props("inline")
            with ui.row().classes("w-full gap-2"):
                row_input = ui.number("行", value=1, min=1, max=20).classes("flex-1")
                col_input = ui.number("列", value=1, min=1, max=20).classes("flex-1")
                layer_input = ui.number("层", value=1, min=1, max=10).classes("flex-1")
            slot_select = ui.select([], label="已有格位（无库存）").classes("w-full")
            slot_select.set_visibility(False)

            ui.separator().classes("q-my-md")
            ui.label("元件类型与规格").classes("text-subtitle1 q-mb-sm")
            with ui.row().classes("w-full items-end gap-2"):
                part_select = ui.select([], label="物料（元件名称）").classes("flex-grow")
                ui.button("新建元件", icon="add", on_click=part_dialog.open).props(
                    "outline color=primary"
                )
            part_detail = ui.label("").classes("text-caption text-grey q-mb-sm")

            ui.separator().classes("q-my-md")
            ui.label("库存数量").classes("text-subtitle1 q-mb-sm")
            with ui.row().classes("w-full gap-2"):
                qty_input = ui.number("初始数量", value=0, min=0).classes("flex-1")
                min_stock_input = ui.number("最低库存", value=0, min=0).classes("flex-1")
                batch_input = ui.input("批次号（可选）").classes("w-full")

        with asset_panel:
            ui.label("1. 物件信息").classes("text-subtitle1 q-mb-sm")
            asset_name_input = ui.input("名称 *").classes("w-full")
            asset_code_input = ui.input("编号（留空自动生成）").classes("w-full")
            asset_category_select = ui.select(
                {
                    "tool": "工具",
                    "dev_board": "开发板",
                    "camera": "相机",
                    "other": "其他",
                },
                label="类别",
                value="other",
            ).classes("w-full")
            asset_serial_input = ui.input("序列号（可选）").classes("w-full")
            asset_location_input = ui.input("存放位置（可选）").classes("w-full")
            asset_remark_input = ui.input("备注（可选）").classes("w-full")

        asset_panel.set_visibility(prefilled_bind == "asset")
        slot_panel.set_visibility(prefilled_bind != "asset")

        def toggle_bind_panels() -> None:
            is_asset = bind_type_select.value == "asset"
            asset_panel.set_visibility(is_asset)
            slot_panel.set_visibility(not is_asset)

        bind_type_select.on("update:model-value", toggle_bind_panels)

        ui.separator().classes("q-my-md")
        ui.label("RFID 标签绑定").classes("text-subtitle1 q-mb-sm")
        epc_label = ui.label("尚未捕获标签").classes("text-body1 text-grey q-mb-sm")
        with ui.row().classes("w-full gap-2 items-center"):
            epc_display = ui.input("EPC").classes("flex-grow")
            rssi_label = ui.label("RSSI: —").classes("text-caption")
        listen_status = ui.label("请点击下方「开始监听 RFID」").classes(
            "text-caption text-grey q-mb-sm"
        )
        poll_hint = ui.label("").classes("text-caption text-blue-grey q-mb-sm")
        manual_epc = ui.input("或手动输入 EPC").classes("w-full")

        refs["epc_label"] = epc_label
        refs["epc_display"] = epc_display
        refs["manual_epc"] = manual_epc
        refs["rssi_label"] = rssi_label
        refs["listen_status"] = listen_status
        refs["poll_hint"] = poll_hint

        async def start_listen() -> None:
            state["baseline_id"] = await fetch_latest_event_id()
            state["poll_count"] = 0
            state["listening"] = True
            state["captured_epc"] = ""
            epc_display.value = ""
            manual_epc.value = ""
            epc_label.set_text("等待读卡…")
            epc_label.classes(remove="text-green", add="text-grey")
            rssi_label.set_text("RSSI: —")
            listen_status.set_text("● 正在监听，请将 RFID 标签靠近读卡器…")
            listen_status.classes(remove="text-grey text-green", add="text-blue")
            poll_hint.set_text(
                f"基准事件 ID={state['baseline_id']}，请将标签靠近读卡器（实时推送）"
            )

        def apply_manual_epc() -> None:
            epc = (manual_epc.value or "").strip().upper()
            if epc:
                capture_tag(epc, None)

        with ui.row().classes("gap-2 q-mb-md"):
            ui.button("开始监听 RFID", icon="sensors", on_click=start_listen).props(
                "color=primary size=md"
            )
            ui.button("使用手动 EPC", on_click=apply_manual_epc).props("flat")

        ui.separator().classes("q-my-md")

        async def submit() -> None:
            epc = (
                (epc_display.value or "")
                or state.get("captured_epc", "")
                or (manual_epc.value or "")
            ).strip()
            if not epc:
                ui.notify("请先读取或输入 RFID 标签 EPC", type="warning")
                return

            bind = bind_type_select.value or "slot_material"
            payload: dict = {
                "bind_type": bind,
                "rfid_tag_epc": epc.upper(),
            }

            if bind == "asset":
                name = (asset_name_input.value or "").strip()
                if not name:
                    ui.notify("请填写物件名称", type="warning")
                    return
                payload["name"] = name
                code = (asset_code_input.value or "").strip()
                if code:
                    payload["asset_code"] = code
                payload["category"] = asset_category_select.value or "other"
                serial = (asset_serial_input.value or "").strip()
                if serial:
                    payload["serial_no"] = serial
                loc = (asset_location_input.value or "").strip()
                if loc:
                    payload["location"] = loc
                remark = (asset_remark_input.value or "").strip()
                if remark:
                    payload["remark"] = remark
            else:
                if not ctx["bin_options"]:
                    ui.notify("料盒尚未加载完成，请稍候", type="warning")
                    return
                if not ctx["part_options"]:
                    ui.notify("请先选择或新建元件", type="warning")
                    return
                part_id = part_select.value
                cabinet_id = ctx["bin_options"].get(cabinet_select.value)
                if not part_id or not cabinet_id:
                    ui.notify("请选择料盒与物料", type="warning")
                    return
                payload.update(
                    {
                        "part_id": part_id,
                        "cabinet_id": cabinet_id,
                        "quantity": int(qty_input.value or 0),
                        "min_stock": int(min_stock_input.value or 0),
                        "batch_no": batch_input.value or None,
                    }
                )
                if slot_mode.value == "existing" and slot_select.value:
                    slot_id = ctx["slot_id_map"].get(slot_select.value)
                    if slot_id:
                        payload["slot_id"] = slot_id
                else:
                    payload["row_no"] = int(row_input.value or 1)
                    payload["col_no"] = int(col_input.value or 1)
                    payload["layer_no"] = int(layer_input.value or 1)

            try:
                result = await client.register_inventory(payload)
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text
                try:
                    detail = exc.response.json().get("detail", detail)
                except Exception:
                    pass
                ui.notify(f"保存失败: {detail}", type="negative")
                return
            except Exception as exc:
                ui.notify(f"保存失败: {exc}", type="negative")
                return

            if bind == "asset":
                asset = result.get("asset") or {}
                ui.notify(
                    f"已登记非标物件: {asset.get('name')} ({asset.get('asset_code')})",
                    type="positive",
                )
            else:
                item = result.get("slot_item") or result
                ui.notify(
                    f"已入库: {item.get('part_number')} @ {item.get('slot_code')}",
                    type="positive",
                )
            ui.navigate.to("/inventory")

        ui.button("确认绑定并入库", icon="save", on_click=submit).props(
            "color=primary size=lg"
        )

    ui.link("← 返回库存列表", "/inventory").classes("q-ma-md")

    def refresh_part_detail() -> None:
        pid = part_select.value if part_select.value else None
        if pid and pid in ctx["part_meta"]:
            p = ctx["part_meta"][pid]
            cat = p.get("category_name")
            cat_str = f"  |  分类: {cat}" if cat else ""
            part_detail.set_text(
                f"料号: {p.get('part_number') or '—'}  |  封装: {p.get('package') or '—'}  |  "
                f"规格: {p.get('value') or '—'}{cat_str}"
            )
        else:
            part_detail.set_text("暂无物料，请点击「新建元件」添加。")

    async def load_empty_slots() -> None:
        cabinet_id = ctx["bin_options"].get(cabinet_select.value)
        if cabinet_id is None:
            return
        slots = await client.get_slots(cabinet_id=cabinet_id)
        empty = [s for s in slots if not s.get("quantity")]
        if empty:
            ctx["slot_id_map"] = {
                f"{s['slot_code']} (R{s['row_no']}C{s['col_no']})": s["id"] for s in empty
            }
            slot_select.set_options(ctx["slot_id_map"])
            slot_select.value = next(iter(ctx["slot_id_map"]))
        else:
            ctx["slot_id_map"] = {}
            slot_select.set_options({"（暂无空位）": 0})
            slot_select.value = 0

    def toggle_slot_mode() -> None:
        is_existing = slot_mode.value == "existing"
        slot_select.set_visibility(is_existing)
        row_input.set_visibility(not is_existing)
        col_input.set_visibility(not is_existing)
        layer_input.set_visibility(not is_existing)
        if is_existing:
            ui.timer(0.01, load_empty_slots, once=True)

    slot_mode.on("update:model-value", toggle_slot_mode)

    def on_cabinet_change() -> None:
        if slot_mode.value == "existing":
            ui.timer(0.01, load_empty_slots, once=True)

    cabinet_select.on("update:model-value", on_cabinet_change)
    part_select.on("update:model-value", refresh_part_detail)

    async def load_data() -> None:
        try:
            bins = await client.get_bins()
            components = await client.get_components()
            categories = await client.get_categories()
        except Exception as exc:
            load_hint.set_text(f"加载失败: {exc}")
            load_hint.classes(add="text-red")
            return

        if not bins:
            load_hint.set_text("请先在「料盒管理」中创建料盒。")
            load_hint.classes(add="text-orange")
            return

        ctx["bin_options"] = {f"{b['code']} · {b['name']}": b["id"] for b in bins}
        cabinet_select.set_options(ctx["bin_options"])
        cabinet_select.value = next(iter(ctx["bin_options"]))

        ctx["category_options"] = {"（不选分类）": None}
        for cat in categories:
            ctx["category_options"][f"{cat['code']} · {cat['name']}"] = cat["id"]
        part_form["category"].set_options(ctx["category_options"])
        part_form["category"].value = next(iter(ctx["category_options"]))

        apply_component_options(components)

        if prefilled_epc:
            apply_epc_to_form(prefilled_epc, prefilled_rssi)
            if prefilled_bind == "asset":
                load_hint.set_text(
                    f"已从仪表盘带入标签 {_short_epc(prefilled_epc)}，请填写非标物件信息。"
                )
            else:
                load_hint.set_text(
                    f"已从仪表盘带入标签 {_short_epc(prefilled_epc)}，请补全料盒、物料与数量。"
                )
        elif components:
            load_hint.set_text("料盒与物料已就绪，请填写信息并绑定 RFID。")
        else:
            load_hint.set_text("暂无物料，可点击「新建元件」创建后入库。")
            load_hint.classes(add="text-orange")

        rfid_status: dict = {}
        try:
            rfid_status = await client.get_rfid_status()
            if rfid_status.get("enabled"):
                if rfid_status.get("connected"):
                    gateway_status.set_text("● RFID 网关已连接")
                    gateway_status.classes(remove="text-grey text-orange", add="text-green")
                else:
                    gateway_status.set_text(
                        f"● RFID 未连接 ({rfid_status.get('port', '?')})，可改用手动输入 EPC"
                    )
                    gateway_status.classes(remove="text-grey text-green", add="text-orange")
            else:
                gateway_status.set_text("● RFID 网关已禁用")
                gateway_status.classes(remove="text-green text-orange", add="text-grey")
        except Exception:
            gateway_status.set_text("● RFID 状态未知（请重启 main.py 加载最新后端）")
            gateway_status.classes(add="text-orange")

    ui.timer(0.05, load_data, once=True)
    ui.timer(1.0, poll_rfid)
