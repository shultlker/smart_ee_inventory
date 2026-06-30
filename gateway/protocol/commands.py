"""YZ-M40 command frame builders (Host → Reader)."""

from __future__ import annotations

from gateway.protocol.frames import build_frame

# Frame codes from YZ-M40 spec section 2
CMD_QUERY_VERSION = 0x40
CMD_START_INVENTORY = 0x21
CMD_INVENTORY_ONCE = 0x22
CMD_STOP_INVENTORY = 0x23
CMD_SET_WORK_PARAMS = 0x41
CMD_SET_PARAM = 0x48
CMD_GET_PARAM = 0x49
CMD_REBOOT = 0x10
CMD_WRITE_TAG = 0x30
CMD_READ_TAG = 0x31


def start_inventory(address: int = 0x0000) -> bytes:
    """Start continuous tag inventory (0x21)."""
    return build_frame(
        frame_type=0x00,
        address=address,
        frame_code=CMD_START_INVENTORY,
        parameters=b"",
    )


def stop_inventory(address: int = 0x0000) -> bytes:
    """Stop tag inventory (0x23)."""
    return build_frame(
        frame_type=0x00,
        address=address,
        frame_code=CMD_STOP_INVENTORY,
        parameters=b"",
    )


def inventory_once(address: int = 0x0000) -> bytes:
    """Single-shot inventory (0x22), passive mode."""
    return build_frame(
        frame_type=0x00,
        address=address,
        frame_code=CMD_INVENTORY_ONCE,
        parameters=b"",
    )


def query_version(address: int = 0x0000) -> bytes:
    """Query firmware version (0x40)."""
    return build_frame(
        frame_type=0x00,
        address=address,
        frame_code=CMD_QUERY_VERSION,
        parameters=b"",
    )
