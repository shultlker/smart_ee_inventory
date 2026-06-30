"""Bin cabinet status display helpers."""

from __future__ import annotations

from shared.constants import BIN_STATUS_LABELS, BinStatus, SLOT_STATUS_LABELS

_BIN_STATUS_COLORS: dict[str, str] = {
    BinStatus.ACTIVE: "green",
    BinStatus.CHECKED_OUT: "orange",
    BinStatus.CHECKOUT_UNREGISTERED: "red",
    BinStatus.RETURN_UNREGISTERED: "purple",
    BinStatus.EMPTY: "grey",
    BinStatus.OCCUPIED: "blue",
    BinStatus.UNKNOWN: "grey",
    BinStatus.OFFLINE: "grey",
    "inactive": "grey",
    "maintenance": "amber",
}


def bin_status_label(status: str | None) -> str:
    if not status:
        return "—"
    return BIN_STATUS_LABELS.get(status, status)


def bin_status_color(status: str | None) -> str:
    if not status:
        return "grey"
    return _BIN_STATUS_COLORS.get(status, "grey")


__all__ = ["bin_status_color", "bin_status_label"]
