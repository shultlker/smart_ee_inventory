"""Initialize SQLite database: create tables and optionally load seed data."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running as: python scripts/init_db.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect

from backend.db import Base, async_session_factory, engine, upgrade_schema
from scripts.seed_data import seed_all


LEGACY_TABLES = ("bins", "components")


async def create_tables(drop_existing: bool = False) -> None:
    Path("data").mkdir(exist_ok=True)
    async with engine.begin() as conn:
        if drop_existing:
            await conn.run_sync(Base.metadata.drop_all)
            for name in LEGACY_TABLES:
                await conn.exec_driver_sql(f"DROP TABLE IF EXISTS {name}")
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(upgrade_schema)


async def print_summary() -> None:
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    print(f"Tables ({len(tables)}): {', '.join(sorted(tables))}")


async def init(*, seed: bool = True, drop: bool = False) -> None:
    await create_tables(drop_existing=drop)
    print("Database schema created: data/inventory.db")

    if seed:
        async with async_session_factory() as session:
            await seed_all(session)
        print(
            "Seed data loaded: 3 parts, BIN-TEST (2 RFID slots + 1 plain slot), "
            "1 demo asset (EPC …9A59E)."
        )

    await print_summary()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize Smart EE Inventory database")
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Only create tables, skip demo seed data",
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop all tables before recreate (destructive)",
    )
    args = parser.parse_args()
    asyncio.run(init(seed=not args.no_seed, drop=args.drop))


if __name__ == "__main__":
    main()
