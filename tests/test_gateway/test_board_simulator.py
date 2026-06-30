"""Tests for YZ-M40 board simulator protocol logic."""

from gateway.board_simulator import (
    BoardSimulator,
    HeldTag,
    drain_command_frames,
    resolve_epc_alias,
)
from gateway.protocol.commands import start_inventory, stop_inventory
from gateway.protocol.frames import decode_frame, parse_frame


def test_drain_command_frames_partial_and_complete() -> None:
    cmd = start_inventory(0)
    buf = bytearray(cmd[:5])
    assert drain_command_frames(buf) == []
    assert len(buf) == 5

    buf.extend(cmd[5:])
    frames = drain_command_frames(buf)
    assert len(frames) == 1
    assert frames[0] == cmd
    assert len(buf) == 0


def test_simulator_start_stop_inventory() -> None:
    sim = BoardSimulator(_log=lambda _: None)
    sim.handle_command(start_inventory(0))
    assert sim.inventory_active
    resp = decode_frame(sim.outbox[0])
    assert resp is not None
    assert resp.frame_code == 0x21

    sim.clear_outbox()
    sim.handle_command(stop_inventory(0))
    assert not sim.inventory_active
    resp = decode_frame(sim.outbox[0])
    assert resp is not None
    assert resp.frame_code == 0x23


def test_simulator_emit_and_hold_on_start() -> None:
    sim = BoardSimulator(_log=lambda _: None)
    epc = "E28011704000021CCCF9A58E"
    sim.held[epc] = HeldTag(epc=epc, rssi=-60)
    sim.handle_command(start_inventory(0))

    tag_frames = [parse_frame(raw) for raw in sim.outbox[1:]]
    assert any(tags and tags[0].epc == epc for tags in tag_frames if tags)


def test_resolve_epc_alias() -> None:
    assert resolve_epc_alias("r10k") == "E28011704000021CCCF9A58E"
    assert resolve_epc_alias("E28068940000502244813C7D") == "E28068940000502244813C7D"
