"""Global RFID / inventory operation handlers — active on every page."""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

from nicegui import context, ui

from frontend.components.asset_confirm import mount_asset_confirm_dialog
from frontend.components.presence_confirm import mount_presence_confirm_dialog
from frontend.services import ApiClient
from frontend.services.event_listener import EventBusListener
from shared.constants import EventType

ConfirmedCallback = Callable[[], Awaitable[None] | None]
OperationCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

_hubs: dict[str, GlobalInventoryEventHub] = {}

# 入库绑定页 / 已跳转绑定时，抑制「未登记标签」弹窗（秒）
_UNBOUND_SNOOZE_AFTER_GOTO_REGISTER = 3600.0
_REGISTER_ROUTE = "/inventory/register"


def _current_path() -> str:
    try:
        request = context.client.request
        url = getattr(request, "url", None)
        raw = getattr(url, "path", None) if url is not None else None
        if not isinstance(raw, str):
            return "/"
        return raw.rstrip("/") or "/"
    except Exception:
        return "/"


def _is_register_route() -> bool:
    path = _current_path()
    return path == _REGISTER_ROUTE or path.startswith(f"{_REGISTER_ROUTE}/")


def _short_epc(epc: str, head: int = 12, tail: int = 6) -> str:
    epc = epc.strip().upper()
    if len(epc) <= head + tail + 1:
        return epc
    return f"{epc[:head]}…{epc[-tail:]}"


class GlobalInventoryEventHub:
    """Per-browser-tab singleton: confirm dialogs + EventBus listener."""

    def __init__(self, client: ApiClient) -> None:
        self.client = client
        self._confirmed_callbacks: dict[str, ConfirmedCallback] = {}
        self._operation_callbacks: dict[str, OperationCallback] = {}
        self._unbound_state: dict[str, Any] = {
            "dismissed_epcs": set(),
            "prompted_at": {},
            "snoozed_until": {},
            "dialog_open": False,
            "pending_epc": "",
            "pending_rssi": None,
        }
        self._presence_confirm = mount_presence_confirm_dialog(
            client, on_confirmed=self._notify_confirmed
        )
        self._asset_confirm = mount_asset_confirm_dialog(
            client, on_confirmed=self._notify_confirmed
        )
        self._mount_unbound_tag_dialog()
        self._listener = EventBusListener(self._on_bus_event)
        self._listener.start()
        ui.timer(5.0, self._poll_pending_operations)

    @property
    def presence_confirm(self) -> dict[str, Any]:
        return self._presence_confirm

    def open_for_operation(self, op: dict[str, Any]) -> None:
        self._presence_confirm["open_for_operation"](op)

    def on_confirmed(self, key: str, callback: ConfirmedCallback) -> None:
        self._confirmed_callbacks[key] = callback

    def off_confirmed(self, key: str) -> None:
        self._confirmed_callbacks.pop(key, None)

    def on_inventory_operation(self, key: str, callback: OperationCallback) -> None:
        self._operation_callbacks[key] = callback

    def off_inventory_operation(self, key: str) -> None:
        self._operation_callbacks.pop(key, None)

    async def _notify_confirmed(self) -> None:
        for callback in list(self._confirmed_callbacks.values()):
            result = callback()
            if inspect.isawaitable(result):
                await result

    async def _notify_inventory_operation(self, payload: dict[str, Any]) -> None:
        for callback in list(self._operation_callbacks.values()):
            result = callback(payload)
            if inspect.isawaitable(result):
                await result

    def _mount_unbound_tag_dialog(self) -> None:
        dialog = ui.dialog()
        state = self._unbound_state

        def _on_hide() -> None:
            state["dialog_open"] = False

        dialog.on("hide", _on_hide)

        with dialog:
            with ui.card().classes("p-4 w-full max-w-md"):
                title = ui.label("检测到未登记标签").classes("text-h6")
                short_label = ui.label("").classes("text-subtitle1 text-primary")
                epc_label = ui.label("").classes("text-caption font-mono text-grey q-mb-xs")
                rssi_label = ui.label("").classes("text-caption text-grey")
                ui.label("该标签尚未入库绑定，是否跳转到入库页面？").classes("text-body2 q-mt-sm q-mb-md")

                def dismiss() -> None:
                    epc = state["pending_epc"]
                    if epc:
                        state["dismissed_epcs"].add(epc)
                    state["dialog_open"] = False
                    dialog.close()

                def goto_register() -> None:
                    epc = state["pending_epc"]
                    if not epc:
                        dialog.close()
                        return
                    rssi = state["pending_rssi"]
                    state["dialog_open"] = False
                    dialog.close()
                    self.snooze_unbound_epc(epc)
                    query = f"epc={quote(epc)}"
                    if rssi is not None:
                        query += f"&rssi={rssi}"
                    ui.navigate.to(f"/inventory/register?{query}")

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("忽略", on_click=dismiss).props("flat")
                    ui.button("入库绑定", icon="nfc", on_click=goto_register).props("color=primary")

        self._unbound_dialog = dialog
        self._unbound_ui = {
            "title": title,
            "short": short_label,
            "epc": epc_label,
            "rssi": rssi_label,
        }

    def snooze_unbound_epc(self, epc: str, *, seconds: float = _UNBOUND_SNOOZE_AFTER_GOTO_REGISTER) -> None:
        """Suppress unbound-tag dialog for this EPC (e.g. while user is on register page)."""
        normalized = (epc or "").strip().upper()
        if not normalized:
            return
        self._unbound_state["snoozed_until"][normalized] = time.monotonic() + max(seconds, 0.0)
        if self._unbound_state.get("pending_epc") == normalized and self._unbound_state.get("dialog_open"):
            self._unbound_state["dialog_open"] = False
            self._unbound_dialog.close()

    def _should_prompt_unbound(self, epc: str) -> bool:
        if _is_register_route():
            return False
        snoozed_until = self._unbound_state["snoozed_until"].get(epc, 0.0)
        if time.monotonic() < snoozed_until:
            return False
        if epc in self._unbound_state["dismissed_epcs"]:
            return False
        last = self._unbound_state["prompted_at"].get(epc, 0.0)
        if time.monotonic() - last < 2.0:
            return False
        return True

    def _maybe_prompt_unbound_tag(
        self,
        epc: str,
        rssi: int | None,
        *,
        cabinet_id: int | None,
        slot_id: int | None,
        asset_id: int | None = None,
    ) -> None:
        if cabinet_id or slot_id or asset_id:
            return
        epc = epc.strip().upper()
        if not epc or epc == "?":
            return
        state = self._unbound_state
        if not self._should_prompt_unbound(epc) or state["dialog_open"]:
            return
        state["pending_epc"] = epc
        state["pending_rssi"] = rssi
        state["prompted_at"][epc] = time.monotonic()
        state["dialog_open"] = True
        self._unbound_ui["short"].set_text(_short_epc(epc))
        self._unbound_ui["epc"].set_text(epc)
        rssi_str = f"{rssi} dBm" if rssi is not None else "—"
        self._unbound_ui["rssi"].set_text(f"信号强度: {rssi_str}")
        self._unbound_ui["title"].set_text("检测到未登记标签")
        self._unbound_dialog.open()

    async def _on_bus_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if event_type == EventType.TAG_READ:
            epc = (payload.get("epc") or "").strip()
            if not epc:
                return
            if payload.get("entity_type") == "asset" and payload.get("asset_id"):
                await self._asset_confirm["open_for_tag"](payload)
                return
            self._maybe_prompt_unbound_tag(
                epc,
                payload.get("rssi"),
                cabinet_id=payload.get("cabinet_id"),
                slot_id=payload.get("slot_id"),
                asset_id=payload.get("asset_id"),
            )
            return

        if event_type == EventType.PRESENCE_CONFIRM_REQUIRED:
            self._presence_confirm["open_for_operation"](payload)
            await self._notify_confirmed()
            return

        if event_type == EventType.INVENTORY_OPERATION:
            await self._notify_inventory_operation(payload)

    async def _poll_pending_operations(self) -> None:
        try:
            pending = await self.client.get_inventory_operations(limit=10, status="pending")
        except Exception:
            return
        for op in pending:
            self._presence_confirm["open_for_operation"](op)
            break


def ensure_global_inventory_events(client: ApiClient | None = None) -> GlobalInventoryEventHub:
    """Mount global RFID handlers once per browser tab (NiceGUI client)."""
    client_id = context.client.id
    hub = _hubs.get(client_id)
    if hub is not None:
        return hub
    if client is None:
        client = ApiClient()
    hub = GlobalInventoryEventHub(client)
    _hubs[client_id] = hub

    def _cleanup() -> None:
        _hubs.pop(client_id, None)

    context.client.on_disconnect(_cleanup)
    return hub
