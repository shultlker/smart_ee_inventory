from config.network import is_port_available, resolve_listen_port


def test_resolve_preferred_port_when_free() -> None:
    port, fallback = resolve_listen_port("127.0.0.1", 58765)
    assert port == 58765
    assert fallback is False


def test_resolve_fallback_when_preferred_busy(monkeypatch) -> None:
    def fake_available(host: str, port: int) -> bool:
        return port == 58766

    monkeypatch.setattr("config.network.is_port_available", fake_available)
    port, fallback = resolve_listen_port("127.0.0.1", 8080, fallbacks=(58766,))
    assert port == 58766
    assert fallback is True
