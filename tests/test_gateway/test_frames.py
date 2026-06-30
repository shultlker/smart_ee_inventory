import pytest

from gateway.protocol.commands import (
    inventory_once,
    query_version,
    start_inventory,
    stop_inventory,
)
from gateway.protocol.frames import (
    FrameBuffer,
    calculate_checksum,
    decode_frame,
    parse_frame,
)

# Spec section 3.1 — tag upload notification (0x80)
TAG_UPLOAD_FRAME = bytes.fromhex(
    "5246020000800019"
    "5017"
    "010CE2000017021701992390217D"
    "0501C3"
    "06043D000000"
    "4C"
)

# Spec section 2.2 — start inventory command
START_INVENTORY_CMD = bytes.fromhex("524600000021000047")

# Spec section 2.3 — response to start inventory
START_INVENTORY_RESP = bytes.fromhex("52460100002100030701003B")


def test_checksum_start_inventory_command() -> None:
    assert start_inventory() == START_INVENTORY_CMD
    assert calculate_checksum(START_INVENTORY_CMD[:-1]) == START_INVENTORY_CMD[-1]


def test_checksum_stop_and_once_commands() -> None:
    assert stop_inventory() == bytes.fromhex("524600000023000045")
    assert inventory_once() == bytes.fromhex("524600000022000046")
    assert query_version() == bytes.fromhex("524600000040000028")


def test_parse_tag_upload_notification() -> None:
    tags = parse_frame(TAG_UPLOAD_FRAME)
    assert len(tags) == 1
    assert tags[0].epc == "E2000017021701992390217D"
    assert tags[0].rssi == -61  # 0xC3 signed
    assert tags[0].frame_code == 0x80


def test_build_tag_upload_notification_roundtrip() -> None:
    from gateway.protocol.frames import build_tag_upload_notification

    raw = build_tag_upload_notification(0x0000, "E28011704000021CCCF9A58E", rssi=-61)
    tags = parse_frame(raw)
    assert len(tags) == 1
    assert tags[0].epc == "E28011704000021CCCF9A58E"
    assert tags[0].rssi == -61


def test_decode_frame_rejects_bad_checksum() -> None:
    bad = bytearray(TAG_UPLOAD_FRAME)
    bad[-1] ^= 0xFF
    assert decode_frame(bytes(bad)) is None


def test_decode_response_frame() -> None:
    frame = decode_frame(START_INVENTORY_RESP)
    assert frame is not None
    assert frame.frame_type == 0x01
    assert frame.frame_code == 0x21
    assert frame.parameters[0:3] == bytes([0x07, 0x01, 0x00])


def test_frame_buffer_partial_reads() -> None:
    buf = FrameBuffer()
    mid = len(TAG_UPLOAD_FRAME) // 2
    assert buf.feed(TAG_UPLOAD_FRAME[:mid]) == []
    tags = buf.feed(TAG_UPLOAD_FRAME[mid:])
    assert len(tags) == 1
    assert tags[0].epc == "E2000017021701992390217D"


def test_frame_buffer_skips_garbage_before_header() -> None:
    buf = FrameBuffer()
    tags = buf.feed(b"\x00\xff" + TAG_UPLOAD_FRAME)
    assert len(tags) == 1


def test_frame_buffer_keeps_partial_r_prefix() -> None:
    buf = FrameBuffer()
    # 第一包：帧被截断，末尾只剩 'R'
    assert buf.feed(TAG_UPLOAD_FRAME[:27]) == []
    # 第二包：补全帧头
    tags = buf.feed(TAG_UPLOAD_FRAME[27:])
    assert len(tags) == 1
    assert tags[0].epc == "E2000017021701992390217D"


def test_parse_frame_empty() -> None:
    assert parse_frame(b"") == []
