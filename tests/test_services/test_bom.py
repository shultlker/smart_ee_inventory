from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.bom_service import (
    analyze_parsed_bom,
    import_bom_csv,
    parse_bom_csv,
    preview_bom_csv,
)
from scripts.seed_data import seed_all

_DEMO_CSV = Path(__file__).resolve().parents[2] / "scripts" / "demo_bom.csv"


def test_parse_bom_csv_demo_format() -> None:
    text = _DEMO_CSV.read_text(encoding="utf-8")
    parsed = parse_bom_csv(text)
    assert parsed.code == "DEMO-BOM-001"
    assert parsed.name == "演示装配板卡"
    assert parsed.version == "1.0"
    assert len(parsed.lines) == 3
    assert parsed.lines[0].part_number == "TEST-R-10K"
    assert parsed.lines[0].quantity == Decimal("10")


def test_parse_bom_csv_flat_format() -> None:
    text = """bom_code,bom_name,version,part_number,quantity,designators,note
DEMO-FLAT,扁平BOM,2.0,TEST-R-10K,2,R1,
DEMO-FLAT,扁平BOM,2.0,TEST-C-100N,1,C1,
"""
    parsed = parse_bom_csv(text)
    assert parsed.code == "DEMO-FLAT"
    assert len(parsed.lines) == 2


def test_parse_bom_csv_rejects_empty() -> None:
    with pytest.raises(ValueError, match="CSV 为空"):
        parse_bom_csv("   \n  ")


@pytest.mark.asyncio
async def test_preview_bom_with_seed(db_session: AsyncSession) -> None:
    await seed_all(db_session)
    text = _DEMO_CSV.read_text(encoding="utf-8")
    analysis = await preview_bom_csv(db_session, text, kit_qty=1)
    assert analysis["bom_code"] == "DEMO-BOM-001"
    assert len(analysis["lines"]) == 3
    assert analysis["summary"]["ok"] == 3
    assert len(analysis["highlight_slot_ids"]) == 3
    for line in analysis["lines"]:
        assert line["slots"]
        assert line["slots"][0]["row_no"] >= 1


@pytest.mark.asyncio
async def test_import_and_analyze_bom(db_session: AsyncSession) -> None:
    await seed_all(db_session)
    text = _DEMO_CSV.read_text(encoding="utf-8")
    bom = await import_bom_csv(db_session, text)
    assert bom["code"] == "DEMO-BOM-001"
    assert len(bom["lines"]) == 3

    analysis = await preview_bom_csv(db_session, text, kit_qty=2)
    assert analysis["kit_qty"] == 2
    r_line = next(ln for ln in analysis["lines"] if ln["part_number"] == "TEST-R-10K")
    assert r_line["required_qty"] == Decimal("20")


@pytest.mark.asyncio
async def test_import_rejects_unknown_part(db_session: AsyncSession) -> None:
    await seed_all(db_session)
    text = """bom_code,bom_name,version
X-001,测试,1.0
part_number,quantity
UNKNOWN-PART-XYZ,1
"""
    with pytest.raises(ValueError, match="不存在"):
        await import_bom_csv(db_session, text)


@pytest.mark.asyncio
async def test_preview_shows_missing_part(db_session: AsyncSession) -> None:
    await seed_all(db_session)
    text = """bom_code,bom_name,version
X-002,测试,1.0
part_number,quantity
UNKNOWN-PART-XYZ,1
TEST-R-10K,1
"""
    analysis = await preview_bom_csv(db_session, text)
    missing = [ln for ln in analysis["lines"] if ln["status"] == "missing_part"]
    assert len(missing) == 1
    ok = [ln for ln in analysis["lines"] if ln["status"] == "ok"]
    assert len(ok) == 1
