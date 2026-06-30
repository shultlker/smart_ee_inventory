#!/usr/bin/env python3
"""YZ-M40 RFID 串口通讯测试工具。

用法示例:
    python scripts/test_rfid_serial.py list
    python scripts/test_rfid_serial.py version -p COM11
    python scripts/test_rfid_serial.py -p COM11 version   # 两种顺序均可
    python scripts/test_rfid_serial.py monitor -p COM11 -d 30

cd D:\smart_ee_inventory
.\.venv\Scripts\Activate.ps1

# 查看可用串口
python scripts\test_rfid_serial.py list

# 连通性测试（发 0x40 查版本）
python scripts\test_rfid_serial.py ping --port COM11

# 查询固件版本
python scripts\test_rfid_serial.py version -p COM11

# 单次盘存（被动模式）
python scripts\test_rfid_serial.py once -p COM11

# 连续监听 30 秒（自动 start → 监听 → stop）
python scripts\test_rfid_serial.py monitor -p COM11 -d 30

# 发送原始十六进制帧
python scripts\test_rfid_serial.py raw -p COM11 --hex "524600000021000047"

默认从 .env 读取 RFID_SERIAL_PORT、RFID_BAUD_RATE、RFID_DEVICE_ADDRESS。
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import serial
from serial.tools import list_ports

from config import get_settings
from gateway.protocol.commands import (
    inventory_once,
    query_version,
    start_inventory,
    stop_inventory,
)
from gateway.protocol.frames import (
    FRAME_CODE_OFFLINE_TAG_UPLOAD,
    FRAME_CODE_TAG_UPLOAD,
    FRAME_TYPE_COMMAND,
    FRAME_TYPE_NOTIFICATION,
    FRAME_TYPE_RESPONSE,
    TLV_STATUS,
    FrameBuffer,
    RfidFrame,
    RfidTag,
    calculate_checksum,
    decode_frame,
    parse_tag_from_parameters,
)

FRAME_TYPE_NAMES = {
    FRAME_TYPE_COMMAND: "命令",
    FRAME_TYPE_RESPONSE: "响应",
    FRAME_TYPE_NOTIFICATION: "通知",
}

FRAME_CODE_NAMES = {
    0x10: "重启",
    0x21: "开始盘存",
    0x22: "单次盘存",
    0x23: "停止盘存",
    0x30: "写标签",
    0x31: "读标签",
    0x40: "查询版本",
    0x41: "设置工作参数",
    0x48: "设置单参数",
    0x49: "查询单参数",
    FRAME_CODE_TAG_UPLOAD: "标签上传",
    FRAME_CODE_OFFLINE_TAG_UPLOAD: "离线标签上传",
}


def hex_str(data: bytes) -> str:
    return data.hex(" ").upper()


def list_serial_ports() -> None:
    ports = list(list_ports.comports())
    if not ports:
        print("未发现可用串口。")
        return
    print(f"{'端口':<10} {'描述'}")
    print("-" * 60)
    for p in ports:
        print(f"{p.device:<10} {p.description}")


def status_from_parameters(parameters: bytes) -> str | None:
    if len(parameters) >= 3 and parameters[0] == TLV_STATUS:
        code = parameters[2]
        return "成功" if code == 0x00 else f"失败(0x{code:02X})"
    return None


def format_frame(frame: RfidFrame, raw: bytes) -> str:
    type_name = FRAME_TYPE_NAMES.get(frame.frame_type, f"0x{frame.frame_type:02X}")
    code_name = FRAME_CODE_NAMES.get(frame.frame_code, f"0x{frame.frame_code:02X}")
    lines = [
        f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
        f"{type_name} | 地址=0x{frame.address:04X} | {code_name}",
        f"  RAW: {hex_str(raw)}",
    ]
    status = status_from_parameters(frame.parameters)
    if status:
        lines.append(f"  状态: {status}")
    tags = parse_tag_from_parameters(frame.parameters, frame.frame_code)
    for i, tag in enumerate(tags, 1):
        rssi = f"{tag.rssi} dBm" if tag.rssi is not None else "N/A"
        lines.append(f"  标签#{i}: EPC={tag.epc}  RSSI={rssi}")
    if not tags and frame.parameters:
        lines.append(f"  参数({len(frame.parameters)}B): {hex_str(frame.parameters)}")
    return "\n".join(lines)


def drain_all_frames(buffer: FrameBuffer) -> list[tuple[RfidFrame, bytes]]:
    """从 FrameBuffer 内部缓冲提取并解码所有完整帧（含响应帧）。"""
    results: list[tuple[RfidFrame, bytes]] = []
    buf = buffer._buffer  # noqa: SLF001 — 测试脚本需要完整帧输出

    while True:
        start = buf.find(b"RF")
        if start < 0:
            buf.clear()
            break
        if start > 0:
            del buf[:start]
        if len(buf) < 8:
            break
        param_len = (buf[6] << 8) | buf[7]
        frame_len = 8 + param_len + 1
        if len(buf) < frame_len:
            break
        raw = bytes(buf[:frame_len])
        del buf[:frame_len]
        frame = decode_frame(raw)
        if frame:
            results.append((frame, raw))
    return results


def push_and_drain(buffer: FrameBuffer, chunk: bytes) -> list[tuple[RfidFrame, bytes]]:
    """Append serial bytes and return all complete decoded frames."""
    buffer.push(chunk)
    return drain_all_frames(buffer)


class RfidSerialTester:
    def __init__(
        self,
        port: str,
        baud_rate: int = 115200,
        address: int = 0x0000,
        timeout: float = 0.2,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.address = address
        self.timeout = timeout
        self._serial: serial.Serial | None = None
        self._parser = FrameBuffer()

    def open(self) -> None:
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baud_rate,
            timeout=self.timeout,
        )
        self._serial.reset_input_buffer()
        self._parser = FrameBuffer()
        print(f"已打开串口 {self.port} @ {self.baud_rate} bps，设备地址 0x{self.address:04X}")

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            print("串口已关闭。")
        self._serial = None

    def __enter__(self) -> RfidSerialTester:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def send(self, payload: bytes, label: str = "") -> None:
        if not self._serial:
            raise RuntimeError("串口未打开")
        checksum = calculate_checksum(payload[:-1])
        ok = payload[-1] == checksum
        title = f"发送 {label}" if label else "发送"
        print(f"\n>>> {title}: {hex_str(payload)}  校验={'OK' if ok else 'ERR'}")
        self._serial.write(payload)
        self._serial.flush()

    def read_once(self, wait_s: float = 0.5) -> list[tuple[RfidFrame, bytes]]:
        if not self._serial:
            raise RuntimeError("串口未打开")
        deadline = time.time() + wait_s
        frames: list[tuple[RfidFrame, bytes]] = []
        while time.time() < deadline:
            chunk = self._serial.read(512)
            if chunk:
                frames.extend(push_and_drain(self._parser, chunk))
            elif frames:
                break
            else:
                time.sleep(0.02)
        return frames

    def print_frames(self, frames: list[tuple[RfidFrame, bytes]]) -> list[RfidTag]:
        tags: list[RfidTag] = []
        if not frames:
            print("  (无响应数据)")
            return tags
        for frame, raw in frames:
            print(format_frame(frame, raw))
            tags.extend(parse_tag_from_parameters(frame.parameters, frame.frame_code))
        return tags

    def cmd_version(self) -> None:
        self.send(query_version(self.address), "查询版本 0x40")
        self.print_frames(self.read_once(1.0))

    def cmd_start(self) -> None:
        self.send(start_inventory(self.address), "开始盘存 0x21")
        self.print_frames(self.read_once(1.0))

    def cmd_stop(self) -> None:
        self.send(stop_inventory(self.address), "停止盘存 0x23")
        self.print_frames(self.read_once(1.0))

    def cmd_once(self) -> None:
        self.send(inventory_once(self.address), "单次盘存 0x22")
        tags = self.print_frames(self.read_once(2.0))
        print(f"\n共读到 {len(tags)} 个标签。")

    def cmd_monitor(self, duration: float, dedupe: bool) -> None:
        print(f"\n监听 {duration:.0f} 秒，Ctrl+C 可提前结束…\n")
        seen: set[str] = set()
        tag_count = 0
        end = time.time() + duration
        try:
            while time.time() < end:
                chunk = self._serial.read(512) if self._serial else b""
                if not chunk:
                    time.sleep(0.02)
                    continue
                for frame, raw in push_and_drain(self._parser, chunk):
                    tags = parse_tag_from_parameters(frame.parameters, frame.frame_code)
                    if tags and dedupe:
                        new_tags = [t for t in tags if t.epc not in seen]
                        for t in new_tags:
                            seen.add(t.epc)
                        if not new_tags and frame.frame_type == FRAME_TYPE_NOTIFICATION:
                            continue
                    print(format_frame(frame, raw))
                    print()
                    tag_count += len(tags)
        except KeyboardInterrupt:
            print("\n用户中断。")
        print(f"监听结束，累计标签上报 {tag_count} 次。")

    def cmd_raw(self, hex_payload: str, wait_s: float) -> None:
        payload = bytes.fromhex(hex_payload.replace(" ", ""))
        self.send(payload, "原始帧")
        self.print_frames(self.read_once(wait_s))

    def cmd_loopback(self) -> None:
        """仅验证串口可读写（发送查询版本并等待任意字节）。"""
        self.cmd_version()


def _connection_arguments(settings) -> argparse.ArgumentParser:
    """串口连接参数，作为子命令的 parent parser，可写在子命令之后。"""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--port", "-p", default=settings.rfid_serial_port,
        help=f"串口号 (默认 {settings.rfid_serial_port})",
    )
    parent.add_argument(
        "--baud", "-b", type=int, default=settings.rfid_baud_rate,
        help=f"波特率 (默认 {settings.rfid_baud_rate})",
    )
    parent.add_argument(
        "--address", "-a", type=lambda x: int(x, 0), default=settings.rfid_device_address,
        help=f"设备地址 (默认 0x{settings.rfid_device_address:04X})",
    )
    parent.add_argument("--timeout", type=float, default=0.2, help="串口读超时秒数")
    return parent


def build_parser() -> argparse.ArgumentParser:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="YZ-M40 RFID 串口通讯测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    conn = _connection_arguments(settings)

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出系统可用串口")

    sub.add_parser("version", parents=[conn], help="查询固件版本 (0x40)")
    sub.add_parser("start", parents=[conn], help="开始连续盘存 (0x21)")
    sub.add_parser("stop", parents=[conn], help="停止盘存 (0x23)")
    sub.add_parser("once", parents=[conn], help="单次盘存 (0x22)")
    sub.add_parser("ping", parents=[conn], help="连通性测试（发送查询版本）")

    mon = sub.add_parser("monitor", parents=[conn], help="持续监听并解析上报帧")
    mon.add_argument("--duration", "-d", type=float, default=60.0, help="监听秒数")
    mon.add_argument("--no-dedupe", action="store_true", help="不过滤重复 EPC")

    raw = sub.add_parser("raw", parents=[conn], help="发送自定义十六进制帧")
    raw.add_argument("--hex", required=True, help='帧内容，如 "524600000021000047"')
    raw.add_argument("--wait", type=float, default=1.0, help="等待响应秒数")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        list_serial_ports()
        return

    try:
        with RfidSerialTester(
            port=args.port,
            baud_rate=args.baud,
            address=args.address,
            timeout=args.timeout,
        ) as tester:
            if args.command == "version":
                tester.cmd_version()
            elif args.command == "ping":
                tester.cmd_loopback()
            elif args.command == "start":
                tester.cmd_start()
            elif args.command == "stop":
                tester.cmd_stop()
            elif args.command == "once":
                tester.cmd_once()
            elif args.command == "monitor":
                tester.cmd_start()
                tester.cmd_monitor(args.duration, dedupe=not args.no_dedupe)
                tester.cmd_stop()
            elif args.command == "raw":
                tester.cmd_raw(args.hex, args.wait)
    except serial.SerialException as exc:
        print(f"\n串口错误: {exc}", file=sys.stderr)
        print("提示: 运行 `python scripts/test_rfid_serial.py list` 查看可用端口。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
