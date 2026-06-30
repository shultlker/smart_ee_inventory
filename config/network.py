"""Network helpers for choosing an available listen port."""

from __future__ import annotations

import socket

DEFAULT_FALLBACK_PORTS = (8765, 8090, 8888, 18080, 9080)


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def resolve_listen_port(
    host: str,
    preferred: int,
    fallbacks: tuple[int, ...] = DEFAULT_FALLBACK_PORTS,
) -> tuple[int, bool]:
    """Return (port, was_fallback). Raises OSError if no port is available."""
    if is_port_available(host, preferred):
        return preferred, False

    for port in fallbacks:
        if port != preferred and is_port_available(host, port):
            return port, True

    raise OSError(
        f"无法在 {host} 上绑定端口 {preferred}，"
        f"备选端口 {', '.join(map(str, fallbacks))} 也均不可用。"
        f"请修改 .env 中的 APP_PORT，或结束占用端口的进程。"
    )
