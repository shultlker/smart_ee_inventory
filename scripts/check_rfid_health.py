#!/usr/bin/env python3
"""RFID 与主程序健康检查。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import serial
from serial.tools import list_ports

from config import get_settings
from gateway.protocol.frames import HEADER, calculate_checksum, decode_frame, parse_tag_from_parameters


def check_usb_ports() -> list[str]:
    return [
        p.device
        for p in list_ports.comports()
        if p.vid or (p.description and "USB" in p.description)
    ]


def passive_listen(port: str, baud: int, seconds: float = 5.0) -> tuple[int, int, list[str]]:
    ser = serial.Serial(port, baud, timeout=0.2)
    buffer = bytearray()
    frames = 0
    tags = 0
    epcs: list[str] = []
    deadline = time.time() + seconds
    try:
        while time.time() < deadline:
            chunk = ser.read(512)
            if not chunk:
                continue
            buffer.extend(chunk)
            while True:
                start = buffer.find(HEADER)
                if start < 0:
                    buffer.clear()
                    break
                if start > 0:
                    del buffer[:start]
                if len(buffer) < 9:
                    break
                param_len = (buffer[6] << 8) | buffer[7]
                frame_len = 8 + param_len + 1
                if len(buffer) < frame_len:
                    break
                raw = bytes(buffer[:frame_len])
                del buffer[:frame_len]
                if raw[-1] != calculate_checksum(raw[:-1]):
                    continue
                frame = decode_frame(raw)
                if not frame:
                    continue
                frames += 1
                for tag in parse_tag_from_parameters(frame.parameters, frame.frame_code):
                    tags += 1
                    if tag.epc not in epcs:
                        epcs.append(tag.epc)
    finally:
        ser.close()
    return frames, tags, epcs


def main() -> int:
    settings = get_settings()
    usb_ports = check_usb_ports()
    issues: list[str] = []
    ok: list[str] = []

    print("=" * 60)
    print("Smart EE Inventory — RFID 健康检查")
    print("=" * 60)

    print(f"\n[配置]")
    print(f"  RFID_ENABLED              = {settings.rfid_enabled}")
    print(f"  RFID_SERIAL_PORT          = {settings.rfid_serial_port}")
    print(f"  RFID_BAUD_RATE            = {settings.rfid_baud_rate}")
    print(f"  RFID_AUTO_START_INVENTORY = {settings.rfid_auto_start_inventory}")
    print(f"  APP                       = http://{settings.app_host}:{settings.app_port}")

    print(f"\n[USB 串口] {usb_ports or '(未发现)'}")

    if not settings.rfid_enabled:
        issues.append("RFID_ENABLED=false，主程序 main.py 不会启动网关（仅 Web/API 运行）")

    if settings.rfid_serial_port not in usb_ports and usb_ports:
        issues.append(
            f"RFID_SERIAL_PORT={settings.rfid_serial_port} 不是当前 USB 设备，"
            f"建议改为 {usb_ports[0]}"
        )

    print(f"\n[串口连通性] 尝试打开 {settings.rfid_serial_port} ...")
    try:
        frames, tag_count, epcs = passive_listen(
            settings.rfid_serial_port, settings.rfid_baud_rate, seconds=5.0
        )
        ok.append(f"串口 {settings.rfid_serial_port} 可打开")
        if frames > 0:
            ok.append(f"5 秒内收到 {frames} 帧 / {tag_count} 次标签上报")
            for epc in epcs:
                ok.append(f"  EPC: {epc}")
        else:
            issues.append("串口可打开但 5 秒内未收到 YZ-M40 帧（确认模块在读卡、天线范围内有标签）")
    except serial.SerialException as exc:
        msg = str(exc)
        if "PermissionError" in msg or "拒绝" in msg or "13," in msg:
            issues.append(
                f"无法打开 {settings.rfid_serial_port}：端口被其他程序占用\n"
                "  → 请关闭 PyCharm 串口监视、test_rfid_serial.py、其他 main.py 实例后重试"
            )
        elif "COM3" in settings.rfid_serial_port or "121" in msg:
            issues.append(f"无法打开 {settings.rfid_serial_port}：{exc}\n  → 端口不存在或设备未连接")
        else:
            issues.append(f"串口错误: {exc}")

    try:
        import httpx

        url = f"http://{settings.app_host}:{settings.app_port}/api/v1/bins"
        resp = httpx.get(url, timeout=3.0)
        if resp.status_code == 200:
            ok.append(f"主程序 API 正常 ({url})")
        else:
            issues.append(f"API 返回 HTTP {resp.status_code}")
    except Exception as exc:
        issues.append(f"主程序未运行或不可达: {exc}")

    print("\n[结果]")
    for line in ok:
        print(f"  [OK] {line}")
    for line in issues:
        print(f"  [!!] {line}")

    if not issues:
        print("\n整体状态: 正常")
        return 0
    print(f"\n整体状态: 发现 {len(issues)} 个问题")
    return 1


if __name__ == "__main__":
    sys.exit(main())
