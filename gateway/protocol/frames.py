"""YZ-M40 UHF reader binary protocol (RF frame + TLV).

Spec: YZ-M40读写器模块规格书 V1.4
Frame: Header('RF') | Type | Addr(2) | Code | ParamLen(2) | Parameters | Checksum
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

HEADER = b"RF"
HEADER_LEN = 2
FIXED_HEADER_LEN = 8  # through Param Length LSB (checksum follows parameters)

FRAME_TYPE_COMMAND = 0x00
FRAME_TYPE_RESPONSE = 0x01
FRAME_TYPE_NOTIFICATION = 0x02

FRAME_CODE_TAG_UPLOAD = 0x80
FRAME_CODE_OFFLINE_TAG_UPLOAD = 0x81

TLV_EPC = 0x01
TLV_RSSI = 0x05
TLV_TIME = 0x06
TLV_STATUS = 0x07
TLV_TAG = 0x50


@dataclass(frozen=True, slots=True)
class RfidTag:
    epc: str
    rssi: int | None = None
    antenna: int | None = None
    frame_code: int | None = None
    read_time: datetime | None = None


@dataclass
class RfidFrame:
    frame_type: int
    address: int
    frame_code: int
    parameters: bytes


def calculate_checksum(data: bytes) -> int:
    """Two's complement checksum over all bytes before checksum byte."""
    total = sum(data) & 0xFF
    return ((~total) + 1) & 0xFF


def build_frame(
    frame_type: int,
    address: int,
    frame_code: int,
    parameters: bytes = b"",
) -> bytes:
    param_len = len(parameters)
    body = bytes(
        [
            ord("R"),
            ord("F"),
            frame_type & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF,
            frame_code & 0xFF,
            (param_len >> 8) & 0xFF,
            param_len & 0xFF,
        ]
    )
    body += parameters
    return body + bytes([calculate_checksum(body)])


def build_success_response(address: int, frame_code: int) -> bytes:
    """YZ-M40 command response with TLV status success (0x07/0x01/0x00)."""
    return build_frame(
        frame_type=FRAME_TYPE_RESPONSE,
        address=address,
        frame_code=frame_code,
        parameters=bytes([TLV_STATUS, 0x01, 0x00]),
    )


def build_tag_upload_notification(
    address: int,
    epc: str,
    *,
    rssi: int = -55,
    frame_code: int = FRAME_CODE_TAG_UPLOAD,
) -> bytes:
    """Build tag upload notification (type 0x02, code 0x80) for one EPC."""
    epc_hex = epc.strip().upper()
    epc_bytes = bytes.fromhex(epc_hex)
    nested = bytes([TLV_EPC, len(epc_bytes)]) + epc_bytes
    nested += bytes([TLV_RSSI, 0x01, rssi & 0xFF])
    parameters = bytes([TLV_TAG, len(nested)]) + nested
    return build_frame(
        frame_type=FRAME_TYPE_NOTIFICATION,
        address=address,
        frame_code=frame_code,
        parameters=parameters,
    )


def _signed_byte(value: int) -> int:
    return value - 256 if value >= 128 else value


def _parse_time_tlv(value: bytes) -> datetime | None:
    if len(value) == 4:
        # Short timestamp (seconds or partial); keep raw if not full date
        return None
    if len(value) >= 7:
        year = (value[0] << 8) | value[1]
        month, day, hour, minute, second = value[2:7]
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            return None
    return None


def _parse_tlv_block(data: bytes, offset: int = 0) -> tuple[dict[int, bytes], int]:
    """Parse consecutive TLVs; return tag→value map and bytes consumed."""
    tlvs: dict[int, bytes] = {}
    pos = offset
    while pos + 2 <= len(data):
        tag = data[pos]
        length = data[pos + 1]
        end = pos + 2 + length
        if end > len(data):
            break
        tlvs[tag] = data[pos + 2 : end]
        pos = end
    return tlvs, pos - offset


def _tag_from_tlvs(
    tlvs: dict[int, bytes],
    frame_code: int | None = None,
) -> RfidTag | None:
    epc_raw = tlvs.get(TLV_EPC)
    if not epc_raw:
        return None

    rssi: int | None = None
    rssi_raw = tlvs.get(TLV_RSSI)
    if rssi_raw and len(rssi_raw) >= 1:
        rssi = _signed_byte(rssi_raw[0])

    read_time: datetime | None = None
    time_raw = tlvs.get(TLV_TIME)
    if time_raw:
        read_time = _parse_time_tlv(time_raw)

    return RfidTag(
        epc=epc_raw.hex().upper(),
        rssi=rssi,
        antenna=None,
        frame_code=frame_code,
        read_time=read_time,
    )


def parse_tag_from_parameters(parameters: bytes, frame_code: int) -> list[RfidTag]:
    """Extract tags from notification frame parameters (may contain Tag TLV 0x50)."""
    tags: list[RfidTag] = []
    pos = 0
    while pos + 2 <= len(parameters):
        tag_type = parameters[pos]
        length = parameters[pos + 1]
        end = pos + 2 + length
        if end > len(parameters):
            break
        value = parameters[pos + 2 : end]
        if tag_type == TLV_TAG:
            nested, _ = _parse_tlv_block(value, 0)
            parsed = _tag_from_tlvs(nested, frame_code=frame_code)
            if parsed:
                tags.append(parsed)
        elif tag_type == TLV_EPC:
            parsed = _tag_from_tlvs({tag_type: value}, frame_code=frame_code)
            if parsed:
                tags.append(parsed)
        pos = end
    return tags


def parse_frame(raw: bytes) -> list[RfidTag]:
    """Parse one complete RF frame and return any tags inside."""
    frame = decode_frame(raw)
    if frame is None:
        return []
    if frame.frame_type != FRAME_TYPE_NOTIFICATION:
        return []
    if frame.frame_code not in (FRAME_CODE_TAG_UPLOAD, FRAME_CODE_OFFLINE_TAG_UPLOAD):
        return []
    return parse_tag_from_parameters(frame.parameters, frame.frame_code)


def decode_frame(raw: bytes) -> RfidFrame | None:
    """Decode and validate a single complete frame."""
    if len(raw) < FIXED_HEADER_LEN + 1:
        return None
    if raw[0:2] != HEADER:
        return None

    param_len = (raw[6] << 8) | raw[7]
    frame_len = FIXED_HEADER_LEN + param_len + 1
    if len(raw) < frame_len:
        return None

    payload = raw[:frame_len]
    expected = calculate_checksum(payload[:-1])
    if payload[-1] != expected:
        return None

    return RfidFrame(
        frame_type=payload[2],
        address=(payload[3] << 8) | payload[4],
        frame_code=payload[5],
        parameters=payload[FIXED_HEADER_LEN : FIXED_HEADER_LEN + param_len],
    )


@dataclass
class FrameBuffer:
    """Accumulate serial bytes and emit parsed RFID tags."""

    _buffer: bytearray = field(default_factory=bytearray)

    def push(self, data: bytes) -> None:
        """Append raw bytes without consuming frames (use with manual drain)."""
        if data:
            self._buffer.extend(data)

    def feed(self, data: bytes) -> list[RfidTag]:
        if not data:
            return []
        self._buffer.extend(data)
        return self._drain()

    def _drain(self) -> list[RfidTag]:
        tags: list[RfidTag] = []
        while True:
            start = self._buffer.find(HEADER)
            if start < 0:
                # 保留末尾 'R'，可能是下一帧 'RF' 的前缀
                if len(self._buffer) > 0 and self._buffer[-1] == ord("R"):
                    self._buffer[:] = self._buffer[-1:]
                else:
                    self._buffer.clear()
                break
            if start > 0:
                del self._buffer[:start]

            if len(self._buffer) < FIXED_HEADER_LEN:
                break

            param_len = (self._buffer[6] << 8) | self._buffer[7]
            frame_len = FIXED_HEADER_LEN + param_len + 1
            if len(self._buffer) < frame_len:
                break

            frame_bytes = bytes(self._buffer[:frame_len])
            del self._buffer[:frame_len]

            frame = decode_frame(frame_bytes)
            if frame is None:
                continue
            if frame.frame_type == FRAME_TYPE_NOTIFICATION and frame.frame_code in (
                FRAME_CODE_TAG_UPLOAD,
                FRAME_CODE_OFFLINE_TAG_UPLOAD,
            ):
                tags.extend(parse_tag_from_parameters(frame.parameters, frame.frame_code))
        return tags
