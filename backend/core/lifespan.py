from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from backend.core.events import event_bus
from backend.db import Base, async_session_factory, engine, upgrade_schema
from backend.services.epc_binding import lookup_epc_binding
from backend.services import record_rfid_event
from backend.services.operation_service import create_presence_pending_action
from backend.services.presence_watchdog import PresenceWatchdog
from config import get_settings
from gateway import GatewayService
from shared.constants import EventType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

_gateway: GatewayService | None = None
_watchdog: PresenceWatchdog | None = None
_presence_tick_task: asyncio.Task[None] | None = None
_bootstrap_task: asyncio.Task[None] | None = None


async def _lookup_epc_binding(
    session,
    epc: str,
) -> dict:
    """Return binding fields for an EPC if bound in DB."""
    binding = await lookup_epc_binding(session, epc)
    return {
        "entity_type": binding.entity_type,
        "slot_id": binding.slot_id,
        "cabinet_id": binding.cabinet_id,
        "asset_id": binding.asset_id,
    }


async def _persist_rfid_event(
    *,
    epc: str,
    rssi: int | None,
    antenna: int | None,
    slot_id: int | None,
    cabinet_id: int | None,
) -> None:
    try:
        async with async_session_factory() as session:
            await record_rfid_event(
                session,
                epc=epc,
                rssi=rssi,
                antenna=antenna,
                slot_id=slot_id,
                cabinet_id=cabinet_id,
            )
    except Exception:
        logger.exception("Failed to persist RFID event EPC=%s", epc)


async def _handle_presence_transition(epc: str, kind: str) -> None:
    try:
        async with async_session_factory() as session:
            operation = await create_presence_pending_action(session, epc, kind)  # type: ignore[arg-type]
    except Exception:
        logger.exception("Watchdog transition failed EPC=%s kind=%s", epc, kind)
        return

    if operation:
        logger.info(
            "Watchdog pending %s: EPC=%s op_id=%s",
            kind,
            epc,
            operation.get("id"),
        )
        await event_bus.publish(EventType.PRESENCE_CONFIRM_REQUIRED, operation)


async def _process_presence_transitions(epc: str, *, now: float | None = None) -> None:
    if _watchdog is None:
        return
    ts = now if now is not None else time.monotonic()
    for transition in _watchdog.on_tag(epc, now=ts):
        await _handle_presence_transition(transition.epc, transition.kind)


async def _presence_tick_loop() -> None:
    settings = get_settings()
    tick_seconds = settings.rfid_presence_tick_ms / 1000.0
    try:
        while True:
            await asyncio.sleep(tick_seconds)
            if _watchdog is None:
                continue
            now = time.monotonic()
            for transition in _watchdog.tick(now=now, tick_seconds=tick_seconds):
                await _handle_presence_transition(transition.epc, transition.kind)
    except asyncio.CancelledError:
        raise


async def _end_watchdog_bootstrap() -> None:
    await asyncio.sleep(get_settings().rfid_presence_bootstrap_ms / 1000.0)
    if _watchdog is not None:
        now = time.monotonic()
        _watchdog.end_bootstrap(now=now)
        logger.info(
            "RFID presence watchdog bootstrap finished (%d ms, %d tags in zone)",
            get_settings().rfid_presence_bootstrap_ms,
            len(_watchdog.present_epcs),
        )


async def _on_gateway_event(event_type: EventType, payload: dict) -> None:
    if event_type == EventType.TAG_READ:
        epc = payload.get("epc", "")
        rssi = payload.get("rssi")
        antenna = payload.get("antenna")
        logger.info("Gateway event TAG_READ: EPC=%s RSSI=%s", epc, rssi)

        async with async_session_factory() as session:
            binding = await _lookup_epc_binding(session, epc)

        enriched = {
            **payload,
            **binding,
        }
        await event_bus.publish(event_type, enriched)
        asyncio.create_task(
            _persist_rfid_event(
                epc=epc,
                rssi=rssi,
                antenna=antenna,
                slot_id=binding["slot_id"],
                cabinet_id=binding["cabinet_id"],
            )
        )

        settings = get_settings()
        if settings.rfid_presence_enabled and _watchdog is not None:
            await _process_presence_transitions(epc)
        return

    await event_bus.publish(event_type, payload)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _gateway, _watchdog, _presence_tick_task, _bootstrap_task

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(upgrade_schema)

    settings = get_settings()
    if settings.rfid_presence_enabled:
        _watchdog = PresenceWatchdog(
            appear_count=settings.rfid_presence_appear_count,
            disappear_count=settings.rfid_presence_disappear_count,
            miss_grace_seconds=settings.rfid_presence_miss_grace_ms / 1000.0,
        )
        _presence_tick_task = asyncio.create_task(_presence_tick_loop())
        logger.info(
            "RFID presence watchdog enabled: appear=%d disappear=%d tick_ms=%d "
            "miss_grace_ms=%d bootstrap_ms=%d",
            settings.rfid_presence_appear_count,
            settings.rfid_presence_disappear_count,
            settings.rfid_presence_tick_ms,
            settings.rfid_presence_miss_grace_ms,
            settings.rfid_presence_bootstrap_ms,
        )

    if settings.rfid_enabled:
        logger.info(
            "Starting RFID gateway: port=%s baud=%d auto_start_inventory=%s",
            settings.rfid_serial_port,
            settings.rfid_baud_rate,
            settings.rfid_auto_start_inventory,
        )
        _gateway = GatewayService(
            port=settings.rfid_serial_port,
            baud_rate=settings.rfid_baud_rate,
            read_interval_ms=settings.rfid_read_interval_ms,
            device_address=settings.rfid_device_address,
            auto_start_inventory=settings.rfid_auto_start_inventory,
            on_event=_on_gateway_event,
        )
        await _gateway.start()
        app.state.gateway = _gateway
        if settings.rfid_presence_enabled and _watchdog is not None:
            _bootstrap_task = asyncio.create_task(_end_watchdog_bootstrap())
            logger.info(
                "RFID presence bootstrap started (%d ms after gateway ready)",
                settings.rfid_presence_bootstrap_ms,
            )
    else:
        logger.info("RFID gateway disabled (RFID_ENABLED=false)")
        if settings.rfid_presence_enabled and _watchdog is not None:
            _bootstrap_task = asyncio.create_task(_end_watchdog_bootstrap())

    yield

    if _bootstrap_task:
        _bootstrap_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _bootstrap_task
        _bootstrap_task = None

    if _presence_tick_task:
        _presence_tick_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _presence_tick_task
        _presence_tick_task = None

    _watchdog = None

    if _gateway:
        await _gateway.stop()
        _gateway = None

    await engine.dispose()
