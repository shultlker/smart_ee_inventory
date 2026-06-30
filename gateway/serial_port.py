"""Low-level serial port wrapper using pyserial."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import serial

if TYPE_CHECKING:
    from serial import Serial

logger = logging.getLogger(__name__)


class SerialPort:
    """Thread-safe serial connection to the RFID development board."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout: float = 0.05) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self._serial: Serial | None = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        if self.is_open:
            return
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baud_rate,
            timeout=self.timeout,
        )
        self._serial.reset_input_buffer()
        logger.info("Serial port opened: %s @ %d", self.port, self.baud_rate)

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port closed: %s", self.port)
        self._serial = None

    def read(self, size: int = 512) -> bytes:
        if not self._serial:
            raise RuntimeError("Serial port is not open")
        return self._serial.read(size)

    def read_available(self, size: int = 512) -> bytes:
        """Return buffered bytes without blocking when the port is idle."""
        if not self._serial:
            raise RuntimeError("Serial port is not open")
        waiting = self._serial.in_waiting
        if waiting <= 0:
            return b""
        return self._serial.read(min(size, waiting))

    def write(self, data: bytes) -> int:
        if not self._serial:
            raise RuntimeError("Serial port is not open")
        written = self._serial.write(data)
        self._serial.flush()
        return written
