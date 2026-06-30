"""Single-zone RFID presence watchdog (appear / disappear debouncing)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PresenceKind = Literal["appear", "disappear"]


@dataclass(frozen=True, slots=True)
class PresenceTransition:
    epc: str
    kind: PresenceKind


class PresenceWatchdog:
    """Track EPC presence in one read zone with debounced transitions."""

    def __init__(
        self,
        *,
        appear_count: int = 2,
        disappear_count: int = 6,
        miss_grace_seconds: float = 1.2,
    ) -> None:
        self._appear_count = max(1, appear_count)
        self._disappear_count = max(1, disappear_count)
        self._miss_grace_seconds = max(0.1, miss_grace_seconds)
        self._present: set[str] = set()
        self._appear_streak: dict[str, int] = {}
        self._miss_streak: dict[str, int] = {}
        self._last_seen: dict[str, float] = {}
        self._bootstrapping = True

    @property
    def bootstrapping(self) -> bool:
        return self._bootstrapping

    def end_bootstrap(self, *, now: float | None = None) -> None:
        """End bootstrap: freeze baseline presence and clear miss counters."""
        self._bootstrapping = False
        ts = now if now is not None else 0.0
        self._miss_streak.clear()
        self._appear_streak.clear()
        if ts > 0:
            for epc in self._present:
                self._last_seen[epc] = ts

    def on_tag(self, epc: str, *, now: float) -> list[PresenceTransition]:
        epc = epc.strip().upper()
        if not epc:
            return []

        self._last_seen[epc] = now
        self._miss_streak[epc] = 0

        if epc in self._present:
            self._appear_streak.pop(epc, None)
            return []

        self._appear_streak[epc] = self._appear_streak.get(epc, 0) + 1
        if self._appear_streak[epc] < self._appear_count:
            return []

        self._present.add(epc)
        self._appear_streak.pop(epc, None)
        if self._bootstrapping:
            return []
        return [PresenceTransition(epc=epc, kind="appear")]

    @property
    def present_epcs(self) -> frozenset[str]:
        return frozenset(self._present)

    def tick(self, *, now: float, tick_seconds: float) -> list[PresenceTransition]:
        if self._bootstrapping:
            return []
        if tick_seconds <= 0:
            return []

        transitions: list[PresenceTransition] = []
        for epc in list(self._present):
            elapsed = now - self._last_seen.get(epc, 0.0)
            if elapsed > self._miss_grace_seconds:
                self._miss_streak[epc] = self._miss_streak.get(epc, 0) + 1
            else:
                self._miss_streak[epc] = 0

            if self._miss_streak.get(epc, 0) < self._disappear_count:
                continue

            self._present.discard(epc)
            self._miss_streak.pop(epc, None)
            self._appear_streak.pop(epc, None)
            transitions.append(PresenceTransition(epc=epc, kind="disappear"))
        return transitions
