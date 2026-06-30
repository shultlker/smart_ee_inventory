#!/usr/bin/env python3
"""YZ-M40 RFID 开发板模拟器（TCP 虚拟串口）。

详见 docs/TESTING.md § RFID 模拟器。
"""

from __future__ import annotations

import argparse
import socket
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_settings
from gateway.board_simulator import (
    DEFAULT_PRESET_TAGS,
    BoardSimulator,
    drain_command_frames,
    resolve_epc_alias,
)


def client_loop(sim: BoardSimulator, conn: socket.socket, addr: tuple) -> None:
    print(f"[sim] 客户端已连接: {addr[0]}:{addr[1]}")
    sim.attach(conn)
    buffer = bytearray()
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            for raw in drain_command_frames(buffer):
                sim.handle_command(raw)
    except OSError as exc:
        print(f"[sim] 连接异常: {exc}")
    finally:
        sim.attach(None)
        conn.close()
        print("[sim] 客户端已断开")


def ticker_loop(sim: BoardSimulator, interval_ms: int, stop: threading.Event) -> None:
    interval = interval_ms / 1000.0
    while not stop.wait(interval):
        sim.tick()


def print_help() -> None:
    print(
        """
命令:
  help                 显示本帮助
  tags                 预设别名与 EPC
  status               连接 / 盘存 / 驻留标签
  emit <epc> [rssi]    立即上报一次
  hold <epc> [rssi]    盘存期间持续上报
  release [epc|all]    取消持续上报
  quit                 退出模拟器

预设别名: r10k, c100n, jetson（对应种子数据三枚标签）
"""
    )


def repl_loop(sim: BoardSimulator, presets: dict[str, str], stop: threading.Event) -> None:
    print_help()
    while not stop.is_set():
        try:
            line = input("rfid> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()

        try:
            if cmd in ("help", "?"):
                print_help()
            elif cmd == "tags":
                for alias, epc in presets.items():
                    print(f"  {alias:8} {epc}")
            elif cmd == "status":
                held = ", ".join(sim.held.keys()) or "(无)"
                print(
                    f"  客户端: {'已连接' if sim.client_connected else '未连接'}"
                    f"  盘存: {'进行中' if sim.inventory_active else '已停止'}"
                )
                print(f"  驻留标签: {held}")
            elif cmd == "emit":
                if len(parts) < 2:
                    print("用法: emit <epc> [rssi]")
                    continue
                epc = resolve_epc_alias(parts[1], presets)
                rssi = int(parts[2]) if len(parts) > 2 else -55
                sim.emit_tag(epc, rssi)
            elif cmd == "hold":
                if len(parts) < 2:
                    print("用法: hold <epc> [rssi]")
                    continue
                epc = resolve_epc_alias(parts[1], presets)
                rssi = int(parts[2]) if len(parts) > 2 else -55
                from gateway.board_simulator import HeldTag

                sim.held[epc] = HeldTag(epc=epc, rssi=rssi)
                print(f"[sim] 驻留 + {epc} RSSI={rssi}")
                if sim.inventory_active:
                    sim.emit_tag(epc, rssi)
            elif cmd == "release":
                if len(parts) > 1 and parts[1].lower() == "all":
                    sim.held.clear()
                    print("[sim] 已清除全部驻留标签")
                elif len(parts) > 1:
                    epc = resolve_epc_alias(parts[1], presets)
                    sim.held.pop(epc, None)
                    print(f"[sim] 已释放 {epc}")
                else:
                    print("用法: release [epc|all]")
            elif cmd in ("quit", "exit", "q"):
                stop.set()
                break
            else:
                print(f"未知命令: {cmd}，输入 help 查看")
        except ValueError as exc:
            print(f"错误: {exc}")


def serve(host: str, port: int, address: int, tick_ms: int) -> None:
    sim = BoardSimulator(address=address)
    stop = threading.Event()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    server.settimeout(1.0)

    print(f"[sim] YZ-M40 模拟器监听 tcp://{host}:{port}")
    print(f"[sim] 主程序请设置 RFID_SERIAL_PORT=socket://{host}:{port}")
    print("[sim] 输入 help 查看交互命令")

    threading.Thread(
        target=ticker_loop, args=(sim, tick_ms, stop), daemon=True, name="rfid-ticker"
    ).start()

    if sys.stdin.isatty():
        threading.Thread(
            target=repl_loop, args=(sim, DEFAULT_PRESET_TAGS, stop), daemon=True, name="rfid-repl"
        ).start()

    try:
        while not stop.is_set():
            try:
                conn, addr = server.accept()
            except (TimeoutError, socket.timeout):
                continue
            except OSError:
                break
            threading.Thread(
                target=client_loop,
                args=(sim, conn, addr),
                daemon=True,
                name="rfid-client",
            ).start()
    except KeyboardInterrupt:
        print("\n[sim] 正在退出…")
    finally:
        stop.set()
        server.close()
        print("[sim] 已停止")


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="YZ-M40 RFID 开发板 TCP 模拟器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9276, help="监听端口 (默认 9276)")
    parser.add_argument(
        "--address",
        type=lambda s: int(s, 0),
        default=settings.rfid_device_address,
        help="设备地址 (默认与 .env RFID_DEVICE_ADDRESS 一致)",
    )
    parser.add_argument(
        "--tick-ms",
        type=int,
        default=200,
        help="盘存期间驻留标签重复上报间隔 ms (默认 200)",
    )
    args = parser.parse_args()
    serve(args.host, args.port, args.address, args.tick_ms)


if __name__ == "__main__":
    main()
