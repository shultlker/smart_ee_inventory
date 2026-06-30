"""In-process event bus for RFID → WebSocket broadcast."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from shared.constants import EventType

Subscriber = Callable[[EventType, dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, callback: Subscriber) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        await asyncio.gather(
            *(callback(event_type, payload) for callback in self._subscribers),
            return_exceptions=True,
        )


event_bus = EventBus()
