"""BOM CSV import and inventory analysis."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import BinSlot, Bom, BomLine, Part
from backend.services.inventory_service import list_inventory_items


@dataclass
class ParsedBomLine:
    line_no: int
    part_number: str
    quantity: Decimal
    designators: str | None
    note: str | None
    is_optional: bool = False


@dataclass
class ParsedBom:
    code: str
    name: str
    version: str
    lines: list[ParsedBomLine]


_LINE_HEADER_ALIASES = {
    "part_number": "part_number",
    "part": "part_number",
    "料号": "part_number",
    "mpn": "part_number",
    "quantity": "quantity",
    "qty": "quantity",
    "数量": "quantity",
    "designators": "designators",
    "designator": "designators",
    "位号": "designators",
    "ref": "designators",
    "note": "note",
    "remark": "note",
    "备注": "note",
    "optional": "optional",
    "is_optional": "optional",
    "可选": "optional",
}


def _norm_header(cell: str) -> str:
    return cell.strip().lower().replace(" ", "_")


def _parse_decimal(value: str) -> Decimal:
    text = value.strip().replace(",", "")
    if not text:
        raise ValueError("数量为空")
    return Decimal(text)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "y", "是", "可选", "optional")


def _header_map(row: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, h in enumerate(row):
        key = _LINE_HEADER_ALIASES.get(_norm_header(h), _norm_header(h))
        out[key] = i
    return out


def _parse_line_rows(rows: list[list[str]], header_map: dict[str, int]) -> list[ParsedBomLine]:
    pn_idx = header_map["part_number"]
    qty_idx = header_map.get("quantity", header_map.get("qty"))
    if qty_idx is None:
        raise ValueError("明细表头须包含 quantity（数量）列")
    des_idx = header_map.get("designators")
    note_idx = header_map.get("note")
    opt_idx = header_map.get("optional")

    lines: list[ParsedBomLine] = []
    line_no = 0
    for row in rows:
        if len(row) <= max(pn_idx, qty_idx):
            continue
        part_number = row[pn_idx].strip()
        if not part_number:
            continue
        line_no += 1
        lines.append(
            ParsedBomLine(
                line_no=line_no,
                part_number=part_number,
                quantity=_parse_decimal(row[qty_idx]),
                designators=row[des_idx].strip()
                if des_idx is not None and des_idx < len(row) and row[des_idx].strip()
                else None,
                note=row[note_idx].strip()
                if note_idx is not None and note_idx < len(row) and row[note_idx].strip()
                else None,
                is_optional=_parse_bool(row[opt_idx])
                if opt_idx is not None and opt_idx < len(row)
                else False,
            )
        )
    return lines


def parse_bom_csv(csv_text: str) -> ParsedBom:
    """Parse demo BOM CSV.

    Recommended layout::

        bom_code,bom_name,version
        DEMO-BOM-001,演示装配,1.0
        part_number,quantity,designators,note
        TEST-R-10K,10,R1;R2,主电路

    Flat layout (BOM fields on each line) is also supported.
    """
    reader = csv.reader(io.StringIO(csv_text.lstrip("\ufeff")))
    rows = [[cell.strip() for cell in row] for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("CSV 为空")

    bom_code = "IMPORT-BOM"
    bom_name = "IMPORT-BOM"
    version = "1.0"
    start_idx = 0

    first_headers = [_norm_header(c) for c in rows[0]]

    if "part_number" in first_headers and ("bom_code" in first_headers or "code" in first_headers):
        header_map = _header_map(rows[0])
        lines = _parse_line_rows(rows[1:], header_map)
        if rows[1:]:
            first = rows[1]
            bom_code = first[header_map.get("bom_code", header_map.get("code", 0))]
            bom_name = first[header_map.get("bom_name", header_map.get("name", 1))]
            ver_idx = header_map.get("version", header_map.get("ver"))
            if ver_idx is not None and ver_idx < len(first) and first[ver_idx]:
                version = first[ver_idx]
    else:
        if first_headers[0] in ("bom_code", "code") and len(rows) > 1:
            meta_values = rows[1]
            if meta_values and _norm_header(meta_values[0]) not in ("part_number", "part", "料号", "mpn"):
                bom_code = meta_values[0] or bom_code
                bom_name = meta_values[1] if len(meta_values) > 1 else bom_code
                if len(meta_values) > 2 and meta_values[2]:
                    version = meta_values[2]
                start_idx = 2
        elif first_headers[0] not in ("part_number", "part", "料号", "mpn") and len(rows) > 1:
            second = [_norm_header(c) for c in rows[1]]
            if second and second[0] in ("part_number", "part", "料号", "mpn"):
                bom_code = rows[0][0] or bom_code
                bom_name = rows[0][1] if len(rows[0]) > 1 else bom_code
                if len(rows[0]) > 2 and rows[0][2]:
                    version = rows[0][2]
                start_idx = 1

        header_idx: int | None = None
        for j in range(start_idx, len(rows)):
            headers = [_norm_header(c) for c in rows[j]]
            if "part_number" in headers or headers[0] in ("part_number", "part", "料号", "mpn"):
                header_idx = j
                break
        if header_idx is None:
            raise ValueError("缺少明细表头行（part_number, quantity, ...）")

        header_map = _header_map(rows[header_idx])
        if "part_number" not in header_map:
            raise ValueError("明细表头须包含 part_number（料号）列")
        if "quantity" not in header_map and "qty" not in header_map:
            raise ValueError("明细表头须包含 quantity（数量）列")
        if "quantity" not in header_map:
            header_map["quantity"] = header_map["qty"]
        lines = _parse_line_rows(rows[header_idx + 1 :], header_map)

    if not lines:
        raise ValueError("未解析到任何 BOM 明细行")

    code = bom_code.strip()
    if not re.match(r"^[\w\-.]+$", code):
        raise ValueError(f"BOM 编号非法: {code}")

    return ParsedBom(
        code=code,
        name=(bom_name or code).strip(),
        version=(version or "1.0").strip(),
        lines=lines,
    )


async def _parts_by_number(session: AsyncSession) -> dict[str, Part]:
    result = await session.execute(select(Part))
    out: dict[str, Part] = {}
    for part in result.scalars().all():
        out[part.part_number.strip().upper()] = part
    return out


async def _inventory_index(session: AsyncSession) -> dict[int, list[dict]]:
    items = await list_inventory_items(session)
    by_part: dict[int, list[dict]] = {}
    for item in items:
        by_part.setdefault(item["part_id"], []).append(item)
    return by_part


def _line_status(required: Decimal, available: int, *, has_part: bool, is_optional: bool) -> str:
    if not has_part:
        return "missing_part"
    if is_optional and available <= 0:
        return "optional_skip"
    if available >= required:
        return "ok"
    if available > 0:
        return "partial"
    return "shortage"


async def analyze_parsed_bom(
    session: AsyncSession,
    parsed: ParsedBom,
    *,
    bom_id: int | None = None,
    kit_qty: int = 1,
) -> dict:
    if kit_qty < 1:
        raise ValueError("套数须 ≥ 1")

    parts_map = await _parts_by_number(session)
    inv_index = await _inventory_index(session)

    summary = {"ok": 0, "partial": 0, "shortage": 0, "missing_part": 0, "optional_skip": 0}
    highlight_slot_ids: set[int] = set()
    line_rows: list[dict] = []

    for pl in parsed.lines:
        key = pl.part_number.strip().upper()
        part = parts_map.get(key)
        required = pl.quantity * kit_qty
        available = 0
        slots: list[dict] = []

        if part:
            for inv in inv_index.get(part.id, []):
                qty = int(inv.get("quantity") or 0)
                avail = int(inv.get("available_qty", qty))
                if qty <= 0:
                    continue
                available += avail
                slots.append(
                    {
                        "slot_id": inv["slot_id"],
                        "slot_code": inv["slot_code"],
                        "cabinet_id": 0,
                        "cabinet_code": inv["cabinet_code"],
                        "cabinet_name": inv["cabinet_name"],
                        "row_no": 0,
                        "col_no": 0,
                        "quantity": qty,
                        "available_qty": avail,
                    }
                )
                highlight_slot_ids.add(inv["slot_id"])

        status = _line_status(required, available, has_part=part is not None, is_optional=pl.is_optional)
        summary[status] = summary.get(status, 0) + 1
        shortage = max(Decimal(0), required - Decimal(available))

        line_rows.append(
            {
                "line_no": pl.line_no,
                "part_id": part.id if part else None,
                "part_number": pl.part_number,
                "part_name": part.name if part else None,
                "required_qty": required,
                "available_qty": available,
                "shortage_qty": shortage,
                "status": status,
                "designators": pl.designators,
                "note": pl.note,
                "is_optional": pl.is_optional,
                "slots": slots,
            }
        )

    analysis = {
        "bom_id": bom_id,
        "bom_code": parsed.code,
        "bom_name": parsed.name,
        "version": parsed.version,
        "kit_qty": kit_qty,
        "lines": line_rows,
        "summary": summary,
        "highlight_slot_ids": sorted(highlight_slot_ids),
    }
    return await _attach_slot_positions(session, analysis)


async def import_bom_csv(session: AsyncSession, csv_text: str) -> dict:
    parsed = parse_bom_csv(csv_text)
    parts_map = await _parts_by_number(session)
    missing = sorted(
        {pl.part_number for pl in parsed.lines if pl.part_number.strip().upper() not in parts_map}
    )
    if missing:
        raise ValueError(f"以下料号在物料库中不存在: {', '.join(missing)}")

    existing = await session.execute(select(Bom).where(Bom.code == parsed.code))
    bom = existing.scalar_one_or_none()
    if bom:
        bom.name = parsed.name
        bom.version = parsed.version
        bom.status = "active"
        await session.execute(delete(BomLine).where(BomLine.bom_id == bom.id))
    else:
        bom = Bom(
            code=parsed.code,
            name=parsed.name,
            version=parsed.version,
            status="active",
        )
        session.add(bom)
        await session.flush()

    for pl in parsed.lines:
        part = parts_map[pl.part_number.strip().upper()]
        session.add(
            BomLine(
                bom_id=bom.id,
                line_no=pl.line_no,
                part_id=part.id,
                quantity=pl.quantity,
                designators=pl.designators,
                note=pl.note,
                is_optional=pl.is_optional,
            )
        )
    await session.commit()

    result = await session.execute(
        select(Bom).options(selectinload(Bom.lines).selectinload(BomLine.part)).where(Bom.id == bom.id)
    )
    bom = result.scalar_one()
    return _bom_to_dict(bom)


async def list_boms(session: AsyncSession) -> list[dict]:
    result = await session.execute(select(Bom).order_by(Bom.code))
    return [
        {
            "id": b.id,
            "code": b.code,
            "name": b.name,
            "version": b.version,
            "status": b.status,
            "created_at": b.created_at,
            "updated_at": b.updated_at,
        }
        for b in result.scalars().all()
    ]


async def get_bom(session: AsyncSession, bom_id: int) -> dict | None:
    result = await session.execute(
        select(Bom).options(selectinload(Bom.lines).selectinload(BomLine.part)).where(Bom.id == bom_id)
    )
    bom = result.scalar_one_or_none()
    if not bom:
        return None
    return _bom_to_dict(bom)


async def analyze_bom_by_id(session: AsyncSession, bom_id: int, *, kit_qty: int = 1) -> dict:
    bom_dict = await get_bom(session, bom_id)
    if not bom_dict:
        raise ValueError("BOM 不存在")
    parsed = ParsedBom(
        code=bom_dict["code"],
        name=bom_dict["name"],
        version=bom_dict["version"],
        lines=[
            ParsedBomLine(
                line_no=ln["line_no"],
                part_number=ln["part_number"] or "",
                quantity=Decimal(str(ln["quantity"])),
                designators=ln.get("designators"),
                note=ln.get("note"),
                is_optional=ln.get("is_optional", False),
            )
            for ln in bom_dict["lines"]
        ],
    )
    return await analyze_parsed_bom(session, parsed, bom_id=bom_id, kit_qty=kit_qty)


async def preview_bom_csv(session: AsyncSession, csv_text: str, *, kit_qty: int = 1) -> dict:
    parsed = parse_bom_csv(csv_text)
    return await analyze_parsed_bom(session, parsed, bom_id=None, kit_qty=kit_qty)


async def _attach_slot_positions(session: AsyncSession, analysis: dict) -> dict:
    slot_ids = {s["slot_id"] for line in analysis["lines"] for s in line["slots"]}
    if not slot_ids:
        return analysis

    result = await session.execute(select(BinSlot).where(BinSlot.id.in_(slot_ids)))
    pos_map = {slot.id: slot for slot in result.scalars().all()}
    highlight: set[int] = set()
    for line in analysis["lines"]:
        for slot in line["slots"]:
            bs = pos_map.get(slot["slot_id"])
            if bs:
                slot["row_no"] = bs.row_no
                slot["col_no"] = bs.col_no
                slot["cabinet_id"] = bs.cabinet_id
                highlight.add(bs.id)
    analysis["highlight_slot_ids"] = sorted(highlight)
    return analysis


def _bom_to_dict(bom: Bom) -> dict:
    lines = []
    for ln in sorted(bom.lines, key=lambda x: x.line_no):
        lines.append(
            {
                "id": ln.id,
                "line_no": ln.line_no,
                "part_id": ln.part_id,
                "quantity": ln.quantity,
                "unit": ln.unit,
                "designators": ln.designators,
                "is_optional": ln.is_optional,
                "note": ln.note,
                "part_number": ln.part.part_number if ln.part else None,
                "part_name": ln.part.name if ln.part else None,
            }
        )
    return {
        "id": bom.id,
        "code": bom.code,
        "name": bom.name,
        "version": bom.version,
        "description": bom.description,
        "status": bom.status,
        "created_at": bom.created_at,
        "updated_at": bom.updated_at,
        "lines": lines,
    }


__all__ = [
    "analyze_bom_by_id",
    "analyze_parsed_bom",
    "get_bom",
    "import_bom_csv",
    "list_boms",
    "parse_bom_csv",
    "preview_bom_csv",
]
