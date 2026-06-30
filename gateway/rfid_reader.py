"""High-level YZ-M40 RFID reader over USB serial."""

from __future__ import annotations

import logging

from gateway.protocol.commands import start_inventory, stop_inventory
from gateway.protocol.frames import FrameBuffer, RfidTag
from gateway.serial_port import SerialPort

logger = logging.getLogger(__name__)

READ_CHUNK_SIZE = 512


class RfidReader:
    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        device_address: int = 0x0000,
        auto_start_inventory: bool = True,
    ) -> None:
        self._serial = SerialPort(port, baud_rate)
        self._device_address = device_address
        self._auto_start_inventory = auto_start_inventory
        self._parser = FrameBuffer()

    @property
    def connected(self) -> bool:
        return self._serial.is_open

    def connect(self) -> None:
        self._serial.open()
        self._parser = FrameBuffer()
        if self._auto_start_inventory:
            cmd = start_inventory(self._device_address)
            self._serial.write(cmd)
            logger.info(
                "Sent YZ-M40 start inventory (0x21) to %s, addr=0x%04X, cmd=%s",
                self._serial.port,
                self._device_address,
                cmd.hex(" ").upper(),
            )
        else:
            logger.info(
                "RFID auto_start_inventory=false, skipped 0x21 on %s (passive listen only)",
                self._serial.port,
            )

    def disconnect(self) -> None:
        if self._serial.is_open and self._auto_start_inventory:
            try:
                self._serial.write(stop_inventory(self._device_address))
                logger.info("Sent YZ-M40 stop inventory (0x23) on %s", self._serial.port)
            except Exception:
                logger.exception("Failed to send stop inventory command")
        self._serial.close()

    def poll_tags(self) -> list[RfidTag]:
        """Drain all currently available serial bytes and return parsed tags."""
        if not self.connected:
            return []
        tags: list[RfidTag] = []
        try:
            while True:
                raw = self._serial.read_available(READ_CHUNK_SIZE)
                if not raw:
                    break
                tags.extend(self._parser.feed(raw))
        except Exception:
            logger.exception("Failed to poll RFID tags")
        return tags
