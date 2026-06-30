"""YZ-M40 RFID development board protocol simulator (for tests and debug CLI)."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from gateway.protocol.commands import (
    CMD_INVENTORY_ONCE,
    CMD_QUERY_VERSION,
    CMD_START_INVENTORY,
    CMD_STOP_INVENTORY,
)
from gateway.protocol.frames import (
    FIXED_HEADER_LEN,
    HEADER,
    build_success_response,
    build_tag_upload_notification,
    decode_frame,
)

DEFAULT_PRESET_TAGS: dict[str, str] = {
    "r10k": "E28011704000021CCCF9A58E",
    "c100n": "E28068940000502244813C7D",
    "jetson": "E28011704000021CCCF9A59E",
}


@dataclass
class HeldTag:
    epc: str
    rssi: int = -55


@dataclass
class BoardSimulator:
    address: int = 0x0000
    inventory_active: bool = False
    held: dict[str, HeldTag] = field(default_factory=dict)
    client_connected: bool = False
    outbox: list[bytes] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _conn: socket.socket | None = field(default=None, repr=False)
    _log: Callable[[str], None] = field(default=print, repr=False)

    def attach(self, conn: socket.socket | None) -> None:
        with self._lock:
            self._conn = conn
            self.client_connected = conn is not None
            if conn is None:
                self.inventory_active = False

    def send(self, data: bytes) -> None:
        self.outbox.append(data)
        with self._lock:
            conn = self._conn
        if conn is None:
            return
        try:
            conn.sendall(data)
        except OSError as exc:
            self._log(f"[sim] 发送失败: {exc}")

    def clear_outbox(self) -> None:
        self.outbox.clear()

    def emit_tag(self, epc: str, rssi: int = -55) -> None:
        epc = epc.strip().upper()
        frame = build_tag_upload_notification(self.address, epc, rssi=rssi)
        self.send(frame)
        self._log(f"[sim] → 标签上报 EPC={epc} RSSI={rssi} dBm")

    def handle_command(self, raw: bytes) -> None:
        frame = decode_frame(raw)
        if frame is None:
            return
        code = frame.frame_code
        if frame.frame_type != 0x00:
            return

        if code == CMD_START_INVENTORY:
            self.inventory_active = True
            self.send(build_success_response(self.address, code))
            self._log("[sim] ← 开始盘存 (0x21)")
            self._emit_held_once()
        elif code == CMD_STOP_INVENTORY:
            self.inventory_active = False
            self.send(build_success_response(self.address, code))
            self._log("[sim] ← 停止盘存 (0x23)")
        elif code == CMD_INVENTORY_ONCE:
            self.send(build_success_response(self.address, code))
            self._log("[sim] ← 单次盘存 (0x22)")
            self._emit_held_once()
        elif code == CMD_QUERY_VERSION:
            self.send(build_success_response(self.address, code))
            self._log("[sim] ← 查询版本 (0x40)")
        else:
            self._log(f"[sim] ← 未模拟命令 0x{code:02X}，已忽略")

    def _emit_held_once(self) -> None:
        with self._lock:
            tags = list(self.held.values())
        for tag in tags:
            self.emit_tag(tag.epc, tag.rssi)

    def tick(self) -> None:
        if not self.inventory_active:
            return
        with self._lock:
            if not self.held:
                return
            tags = list(self.held.values())
        for tag in tags:
            self.emit_tag(tag.epc, tag.rssi)


def drain_command_frames(buffer: bytearray) -> list[bytes]:
    frames: list[bytes] = []
    while True:
        start = buffer.find(HEADER)
        if start < 0:
            buffer.clear()
            break
        if start > 0:
            del buffer[:start]
        if len(buffer) < FIXED_HEADER_LEN:
            break
        param_len = (buffer[6] << 8) | buffer[7]
        frame_len = FIXED_HEADER_LEN + param_len + 1
        if len(buffer) < frame_len:
            break
        frames.append(bytes(buffer[:frame_len]))
        del buffer[:frame_len]
    return frames


def resolve_epc_alias(token: str, presets: dict[str, str] | None = None) -> str:
    """Resolve preset alias or validate raw EPC hex string."""
    catalog = presets or DEFAULT_PRESET_TAGS
    key = token.strip().lower()
    if key in catalog:
        return catalog[key]
    epc = token.strip().upper()
    if len(epc) < 8:
        raise ValueError(f"无效 EPC: {token}")
    return epc
