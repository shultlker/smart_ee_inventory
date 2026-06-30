"""Tests for global RFID / inventory event hub (all NiceGUI pages)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import frontend.services.global_inventory_events as gie_mod
from shared.constants import EventType


@pytest.fixture
def mock_ui_stack():
    mock_ui = MagicMock()
    mock_dialog = MagicMock()
    mock_ui.dialog.return_value = mock_dialog
    card_cm = MagicMock()
    card_cm.__enter__ = MagicMock(return_value=MagicMock())
    card_cm.__exit__ = MagicMock(return_value=False)
    mock_ui.card.return_value = card_cm
    row_cm = MagicMock()
    row_cm.__enter__ = MagicMock(return_value=MagicMock())
    row_cm.__exit__ = MagicMock(return_value=False)
    mock_ui.row.return_value = row_cm
    mock_ui.label.return_value = MagicMock()
    mock_ui.button.return_value = MagicMock()
    mock_ui.timer = MagicMock()

    mock_client_ctx = MagicMock()
    mock_client_ctx.id = "test-client-1"
    mock_client_ctx.on_disconnect = MagicMock()

    mock_ctx = MagicMock()
    mock_ctx.client = mock_client_ctx

    presence = {"open_for_operation": MagicMock()}
    asset = {"open_for_tag": AsyncMock()}

    mock_listener_cls = MagicMock()
    mock_listener = MagicMock()
    mock_listener_cls.return_value = mock_listener

    with (
        patch.object(gie_mod, "ui", mock_ui),
        patch.object(gie_mod, "context", mock_ctx),
        patch.object(gie_mod, "mount_presence_confirm_dialog", return_value=presence),
        patch.object(gie_mod, "mount_asset_confirm_dialog", return_value=asset),
        patch.object(gie_mod, "EventBusListener", mock_listener_cls),
    ):
        gie_mod._hubs.clear()
        yield {
            "presence": presence,
            "asset": asset,
            "listener_cls": mock_listener_cls,
            "listener": mock_listener,
            "dialog": mock_dialog,
        }
        gie_mod._hubs.clear()


def test_ensure_singleton_per_client(mock_ui_stack) -> None:
    hub_a = gie_mod.ensure_global_inventory_events()
    hub_b = gie_mod.ensure_global_inventory_events()
    assert hub_a is hub_b
    mock_ui_stack["listener"].start.assert_called_once()


@pytest.mark.asyncio
async def test_callback_registry_replace_by_key(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    seen: list[str] = []

    hub.on_confirmed("dashboard", lambda: seen.append("dash"))
    hub.on_confirmed("operations", lambda: seen.append("ops"))
    hub.off_confirmed("dashboard")

    await hub._notify_confirmed()
    assert seen == ["ops"]


@pytest.mark.asyncio
async def test_on_bus_event_routes_asset_tag_read(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    payload = {
        "epc": "E28011704000021CCCF9A59E",
        "entity_type": "asset",
        "asset_id": 1,
    }
    await hub._on_bus_event(EventType.TAG_READ, payload)
    mock_ui_stack["asset"]["open_for_tag"].assert_awaited_once_with(payload)
    mock_ui_stack["dialog"].open.assert_not_called()


@pytest.mark.asyncio
async def test_on_bus_event_routes_unbound_tag_read(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    epc = "E28099999999999999999999"
    await hub._on_bus_event(
        EventType.TAG_READ,
        {"epc": epc, "rssi": -55},
    )
    mock_ui_stack["asset"]["open_for_tag"].assert_not_called()
    mock_ui_stack["dialog"].open.assert_called_once()
    assert hub._unbound_state["pending_epc"] == epc


@pytest.mark.asyncio
async def test_on_bus_event_skips_bound_slot_tag_for_unbound_prompt(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    await hub._on_bus_event(
        EventType.TAG_READ,
        {"epc": "E28011704000021CCCF9A58E", "slot_id": 1},
    )
    mock_ui_stack["dialog"].open.assert_not_called()


@pytest.mark.asyncio
async def test_on_bus_event_presence_confirm(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    op = {"id": 9, "status": "pending", "operation": "take_out"}
    refreshed: list[str] = []
    hub.on_confirmed("test", lambda: refreshed.append("ok"))

    await hub._on_bus_event(EventType.PRESENCE_CONFIRM_REQUIRED, op)

    mock_ui_stack["presence"]["open_for_operation"].assert_called_once_with(op)
    assert refreshed == ["ok"]


@pytest.mark.asyncio
async def test_poll_pending_operations(mock_ui_stack) -> None:
    client = MagicMock()
    client.get_inventory_operations = AsyncMock(
        return_value=[{"id": 1, "status": "pending", "operation": "take_out"}]
    )
    hub = gie_mod.GlobalInventoryEventHub(client)
    await hub._poll_pending_operations()
    mock_ui_stack["presence"]["open_for_operation"].assert_called_once()


def test_should_prompt_unbound_respects_dismissed(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    epc = "E280ABCDEF0123456789AB"
    hub._unbound_state["dismissed_epcs"].add(epc)
    assert hub._should_prompt_unbound(epc) is False


def test_should_prompt_unbound_respects_snooze(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    epc = "E280ABCDEF0123456789AB"
    hub.snooze_unbound_epc(epc, seconds=3600)
    assert hub._should_prompt_unbound(epc) is False


def test_should_prompt_unbound_skips_on_register_route(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    epc = "E280ABCDEF0123456789AB"
    with patch.object(gie_mod, "_is_register_route", return_value=True):
        assert hub._should_prompt_unbound(epc) is False


def test_snooze_closes_open_unbound_dialog(mock_ui_stack) -> None:
    hub = gie_mod.GlobalInventoryEventHub(MagicMock())
    epc = "E280ABCDEF0123456789AB"
    hub._unbound_state["pending_epc"] = epc
    hub._unbound_state["dialog_open"] = True
    hub.snooze_unbound_epc(epc)
    assert hub._unbound_state["dialog_open"] is False
    mock_ui_stack["dialog"].close.assert_called_once()


def test_short_epc() -> None:
    assert gie_mod._short_epc("E28011704000021CCCF9A58E") == "E28011704000…F9A58E"
