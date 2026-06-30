"""Subscribe to in-process EventBus updates for NiceGUI pages."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from nicegui import context

from backend.core.events import event_bus
from shared.constants import EventType

EventHandler = Callable[[EventType, dict[str, Any]], Awaitable[None] | None]


class EventBusListener:
    """Wire event_bus events to a page callback; auto-unsubscribe on disconnect."""

    def __init__(self, on_event: EventHandler) -> None:
        self._on_event = on_event
        self._client = context.client
        self._started = False

    async def _dispatch(self, event_type: EventType, payload: dict[str, Any]) -> None:
        with self._client:
            result = self._on_event(event_type, payload)
            if inspect.isawaitable(result):
                await result

    def start(self) -> None:
        if self._started:
            return
        event_bus.subscribe(self._dispatch)
        self._client.on_disconnect(self._stop)
        self._started = True

    def _stop(self) -> None:
        if not self._started:
            return
        event_bus.unsubscribe(self._dispatch)
        self._started = False
