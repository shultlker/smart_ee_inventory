from backend.services.presence_watchdog import PresenceWatchdog


def test_presence_appear_after_reads() -> None:
    wd = PresenceWatchdog(appear_count=2, disappear_count=2, miss_grace_seconds=0.5)
    wd.end_bootstrap()
    assert wd.on_tag("EPC001", now=1.0) == []
    transitions = wd.on_tag("EPC001", now=1.1)
    assert len(transitions) == 1
    assert transitions[0].kind == "appear"
    assert transitions[0].epc == "EPC001"


def test_presence_bootstrap_suppresses_appear() -> None:
    wd = PresenceWatchdog(appear_count=1, disappear_count=2, miss_grace_seconds=0.5)
    assert wd.on_tag("EPC001", now=1.0) == []
    assert "EPC001" in wd.present_epcs
    wd.end_bootstrap(now=1.0)
    assert wd.on_tag("EPC001", now=1.1) == []
    assert wd.on_tag("EPC002", now=2.0)[0].kind == "appear"


def test_bootstrap_tick_does_not_drop_present_or_fire_disappear() -> None:
    wd = PresenceWatchdog(appear_count=1, disappear_count=1, miss_grace_seconds=0.1)
    assert wd.on_tag("EPC001", now=1.0) == []
    assert "EPC001" in wd.present_epcs
    for t in (2.0, 2.2, 2.4, 2.6):
        assert wd.tick(now=t, tick_seconds=0.2) == []
    assert "EPC001" in wd.present_epcs
    wd.end_bootstrap(now=3.0)
    assert wd.on_tag("EPC001", now=3.1) == []


def test_presence_disappear_requires_grace_and_streak() -> None:
    wd = PresenceWatchdog(appear_count=1, disappear_count=2, miss_grace_seconds=1.0)
    wd.end_bootstrap()
    assert wd.on_tag("EPC001", now=1.0)[0].kind == "appear"
    # Within grace window: no disappear
    assert wd.tick(now=1.5, tick_seconds=0.2) == []
    assert wd.tick(now=2.0, tick_seconds=0.2) == []
    # Past grace: two consecutive miss ticks → disappear
    assert wd.tick(now=2.3, tick_seconds=0.2) == []
    transitions = wd.tick(now=2.5, tick_seconds=0.2)
    assert len(transitions) == 1
    assert transitions[0].kind == "disappear"


def test_intermittent_reads_reset_miss_streak() -> None:
    wd = PresenceWatchdog(appear_count=1, disappear_count=3, miss_grace_seconds=0.8)
    wd.end_bootstrap()
    wd.on_tag("EPC001", now=1.0)
    # Brief gap then read again — should not disappear
    assert wd.tick(now=1.5, tick_seconds=0.2) == []
    wd.on_tag("EPC001", now=1.6)
    assert wd.tick(now=2.0, tick_seconds=0.2) == []
