"""Background gateway service: polls RFID and publishes events."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from gateway.rfid_reader import RfidReader
from shared.constants import EventType

logger = logging.getLogger(__name__)

EventCallback = Callable[[EventType, dict[str, Any]], Awaitable[None]]


class GatewayService:
    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        read_interval_ms: int = 50,
        device_address: int = 0x0000,
        auto_start_inventory: bool = True,
        on_event: EventCallback | None = None,
    ) -> None:
        self._reader = RfidReader(
            port,
            baud_rate,
            device_address=device_address,
            auto_start_inventory=auto_start_inventory,
        )
        self._read_interval = read_interval_ms / 1000.0
        self._on_event = on_event
        self._port = port
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._connected = False
        self._offline_warned = False

    @property
    def connected(self) -> bool:
        return self._connected and self._reader.connected

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            self._reader.connect()
            self._connected = True
            logger.info("RFID gateway connected on %s", self._port)
            if self._on_event:
                await self._on_event(EventType.GATEWAY_CONNECTED, {"port": self._port})
        except Exception:
            self._connected = False
            logger.exception(
                "RFID gateway failed to open %s — tags will NOT be received. "
                "Close other programs using this COM port (test_rfid_serial.py, serial monitor).",
                self._port,
            )
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._reader.connected:
            self._reader.disconnect()
        self._connected = False
        if self._on_event:
            await self._on_event(EventType.GATEWAY_DISCONNECTED, {})

    async def _loop(self) -> None:
        while self._running:
            if not self._reader.connected:
                if not self._offline_warned:
                    logger.warning("RFID gateway offline: serial not open, polling skipped")
                    self._offline_warned = True
                await asyncio.sleep(1.0)
                continue

            self._offline_warned = False
            tags = await asyncio.to_thread(self._reader.poll_tags)
            for tag in tags:
                logger.info("RFID tag read: EPC=%s RSSI=%s dBm", tag.epc, tag.rssi)
                if self._on_event:
                    await self._on_event(
                        EventType.TAG_READ,
                        {"epc": tag.epc, "rssi": tag.rssi, "antenna": tag.antenna},
                    )
            if tags:
                continue
            await asyncio.sleep(self._read_interval)
