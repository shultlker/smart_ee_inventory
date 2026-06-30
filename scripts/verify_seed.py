#!/usr/bin/env python3
"""Verify seed data in the local SQLite database."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from backend.db import async_session_factory
from backend.models import Asset, BinCabinet, BinSlot, InventoryItem, Part
from scripts.seed_data import DEMO_ASSETS, SLOT_INVENTORY


async def verify(*, strict: bool) -> int:
    issues: list[str] = []
    ok: list[str] = []

    async with async_session_factory() as session:
        cabinet = (
            await session.execute(select(BinCabinet).where(BinCabinet.code == "BIN-TEST"))
        ).scalar_one_or_none()
        if cabinet is None:
            issues.append("缺少料盒 BIN-TEST，请运行 python scripts/init_db.py --drop")
            _report(ok, issues)
            return 1

        ok.append(f"料盒 BIN-TEST id={cabinet.id} ({cabinet.row_count}×{cabinet.col_count})")

        slots = (
            await session.execute(
                select(BinSlot).where(BinSlot.cabinet_id == cabinet.id).order_by(BinSlot.slot_code)
            )
        ).scalars().all()
        if len(slots) != 3:
            issues.append(f"BIN-TEST 应有 3 个格位，实际 {len(slots)}")

        for slot_code, _, _, part_number, qty, min_stock, expected_epc in SLOT_INVENTORY:
            slot = next((s for s in slots if s.slot_code == slot_code), None)
            if slot is None:
                issues.append(f"缺少格位 {slot_code}")
                continue
            if slot.rfid_tag_epc != expected_epc:
                issues.append(
                    f"{slot_code} EPC 应为 {expected_epc or '(none)'}，"
                    f"实际 {slot.rfid_tag_epc or '(none)'}"
                )
            inv = (
                await session.execute(select(InventoryItem).where(InventoryItem.slot_id == slot.id))
            ).scalar_one_or_none()
            part = (
                await session.execute(select(Part).where(Part.part_number == part_number))
            ).scalar_one_or_none()
            if inv is None or part is None:
                issues.append(f"{slot_code} 缺少库存或物料 {part_number}")
            elif inv.quantity != qty or inv.min_stock != min_stock:
                issues.append(f"{slot_code} 库存数量/最低库存与种子不一致")
            else:
                ok.append(
                    f"格位 {slot_code} · {part_number} qty={qty} EPC={slot.rfid_tag_epc or '-'}"
                )

        for spec in DEMO_ASSETS:
            asset = (
                await session.execute(select(Asset).where(Asset.asset_code == spec["asset_code"]))
            ).scalar_one_or_none()
            if asset is None:
                issues.append(f"缺少非标物件 {spec['asset_code']}")
            elif asset.rfid_tag_epc != spec["rfid_tag_epc"]:
                issues.append(
                    f"{spec['asset_code']} EPC 应为 {spec['rfid_tag_epc']}，"
                    f"实际 {asset.rfid_tag_epc}"
                )
            else:
                ok.append(f"非标 {asset.asset_code} · {asset.name} EPC={asset.rfid_tag_epc}")

    _report(ok, issues)
    if issues and strict:
        return 1
    return 0 if not issues else 2


def _report(ok: list[str], issues: list[str]) -> None:
    print("=" * 60)
    print("Smart EE Inventory — 种子数据校验")
    print("=" * 60)
    for line in ok:
        print(f"  OK  {line}")
    for line in issues:
        print(f"  FAIL  {line}")
    print("-" * 60)
    if issues:
        print(f"结果: {len(issues)} 项异常")
    else:
        print("结果: 全部通过")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify BIN-TEST seed data in inventory.db")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="存在异常时返回退出码 1（默认仅警告返回 2）",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(verify(strict=args.strict)))


if __name__ == "__main__":
    main()
