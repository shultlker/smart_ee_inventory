"""Read-only shelf grid for bin slot status and inventory summary."""

from __future__ import annotations

from nicegui import ui

from frontend.constants.bin_status import bin_status_color, bin_status_label
from shared.constants import SLOT_STATUS_LABELS

_STATUS_LABEL = SLOT_STATUS_LABELS

_STATUS_COLOR = {
    "empty": "grey",
    "occupied": "green",
    "checked_out": "orange",
    "pending_checkout": "amber",
    "pending_return": "blue",
    "checkout_unregistered": "red",
    "return_unregistered": "purple",
    "disabled": "red",
}


def slot_matches_search(slot: dict | None, query: str) -> bool:
    if not query.strip():
        return True
    if not slot:
        return False
    needle = query.strip().lower()
    for field in (
        slot.get("slot_code"),
        slot.get("part_name"),
        slot.get("part_number"),
        slot.get("rfid_tag_epc"),
        slot.get("label"),
    ):
        if field and needle in str(field).lower():
            return True
    return False


def count_search_matches(slots: list[dict], query: str) -> int:
    if not query.strip():
        return len(slots)
    return sum(1 for s in slots if slot_matches_search(s, query))


def _slot_card_classes(
    slot: dict | None,
    *,
    search: str = "",
    highlighted: bool = False,
    bom_highlight: bool = False,
) -> str:
    base = "p-2 min-h-28 flex flex-col gap-0.5"
    if bom_highlight:
        base += " ring-2 ring-blue-8 ring-offset-1"
    elif search.strip():
        if highlighted:
            base += " ring-2 ring-amber-8 ring-offset-1"
        else:
            base += " opacity-35"
    if not slot:
        return f"{base} bg-grey-2"
    status = slot.get("status") or "empty"
    if status == "occupied":
        return f"{base} bg-green-1 border border-green-4"
    if status == "return_unregistered":
        return f"{base} bg-purple-1 border border-purple-4"
    if status == "checked_out":
        return f"{base} bg-orange-1 border border-orange-4"
    if status in ("pending_checkout", "checkout_unregistered"):
        return f"{base} bg-amber-1 border border-amber-5"
    if status == "pending_return":
        return f"{base} bg-blue-1 border border-blue-4"
    if status == "disabled":
        return f"{base} bg-red-1 border border-red-3 opacity-70"
    return f"{base} bg-grey-1 border border-grey-4"


def render_shelf_grid(
    bin_: dict,
    slots: list[dict],
    *,
    edit_link: str | None = "/slots",
    compact: bool = False,
    search: str = "",
    highlight_slot_ids: set[int] | None = None,
) -> None:
    """Render row×col grid for one cabinet. Read-only overview."""
    pad = "q-px-sm" if compact else "q-px-md"
    query = search.strip()
    rows = bin_.get("row_count", 1)
    cols = bin_.get("col_count", 1)
    slot_map = {(s["row_no"], s["col_no"]): s for s in slots}

    occupied = sum(1 for s in slots if s.get("quantity"))
    configured = len(slots)
    total_cells = rows * cols
    match_count = count_search_matches(slots, query)
    bom_ids = highlight_slot_ids or set()
    bom_match_count = sum(1 for s in slots if s.get("id") in bom_ids)

    cabinet_status = bin_.get("status")

    with ui.row().classes(f"w-full {pad} gap-3 items-center q-mb-sm flex-wrap"):
        ui.label(
            f"{bin_['code']} · {bin_['name']}  ({rows}×{cols} = {total_cells} 格)"
        ).classes("text-subtitle2" if compact else "text-subtitle1")
        if cabinet_status and cabinet_status not in ("active",):
            ui.badge(
                bin_status_label(cabinet_status),
                color=bin_status_color(cabinet_status),
            ).props("dense")
        stats = f"已配置 {configured} · 在库 {occupied}"
        if query:
            stats += f" · 匹配 {match_count}"
        if bom_ids:
            stats += f" · BOM 格位 {bom_match_count}"
        ui.label(stats).classes("text-caption text-grey")
        if edit_link:
            ui.link("编辑格位 →", edit_link).classes("text-caption no-underline text-primary")

    with ui.grid(columns=cols).classes(f"w-full {pad} gap-2"):
        for r in range(1, rows + 1):
            for c in range(1, cols + 1):
                slot = slot_map.get((r, c))
                highlighted = bool(query and slot and slot_matches_search(slot, query))
                bom_highlight = bool(slot and slot.get("id") in bom_ids)
                with ui.card().classes(
                    _slot_card_classes(
                        slot,
                        search=query,
                        highlighted=highlighted,
                        bom_highlight=bom_highlight,
                    )
                ):
                    if slot:
                        status = slot.get("status") or "empty"
                        part_name = slot.get("part_name")
                        part_number = slot.get("part_number")
                        has_inventory = bool(part_name or part_number or slot.get("quantity"))

                        if has_inventory:
                            title = part_name or part_number or slot["slot_code"]
                            with ui.row().classes(
                                "w-full items-start justify-between no-wrap gap-1"
                            ):
                                ui.label(title).classes(
                                    "text-body2 font-medium truncate flex-grow leading-tight"
                                )
                                ui.badge(
                                    _STATUS_LABEL.get(status, status),
                                    color=_STATUS_COLOR.get(status, "grey"),
                                ).props("dense")
                            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                                ui.label(slot["slot_code"]).classes(
                                    "text-caption text-grey shrink-0"
                                )
                                if part_name and part_number:
                                    ui.label(part_number).classes(
                                        "text-caption text-grey truncate"
                                    )
                            qty = slot.get("quantity")
                            ui.label(
                                f"数量: {qty if qty is not None else '—'}"
                            ).classes("text-caption")
                        else:
                            with ui.row().classes("w-full items-center justify-between no-wrap"):
                                ui.label(slot["slot_code"]).classes("text-caption text-grey")
                                ui.badge(
                                    _STATUS_LABEL.get(status, status),
                                    color=_STATUS_COLOR.get(status, "grey"),
                                ).props("dense")
                            ui.label("无库存").classes("text-caption text-grey")
                        if slot.get("rfid_tag_epc"):
                            ui.icon("nfc", size="xs").classes("text-blue-5 self-end").tooltip(
                                "已绑定 RFID"
                            )
                    else:
                        ui.label(f"R{r}C{c}").classes("text-caption text-grey")
                        ui.label("未配置").classes("text-caption text-grey-6")
