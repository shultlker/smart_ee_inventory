#!/usr/bin/env python3
"""Run project smoke tests (fast subset + optional seed verify)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_PYTEST_PATHS = [
    "tests/test_gateway",
    "tests/test_frontend/test_global_inventory_events.py",
    "tests/test_services/test_epc_binding.py",
    "tests/test_services/test_seed_data.py",
    "tests/test_services/test_inventory_edit.py",
    "tests/test_services/test_inventory_manage.py::test_slot_tag_bind_rebind_unbind_delete",
    "tests/test_services/test_inventory_manage.py::test_asset_tag_lifecycle",
    "tests/test_api/test_inventory_edit_api.py",
]


def run_pytest(paths: list[str], *, extra: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest", *paths, "-q", *extra]
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart EE Inventory smoke test runner")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run all tests under tests/ (slower)",
    )
    parser.add_argument(
        "--verify-seed",
        action="store_true",
        help="After pytest, run scripts/verify_seed.py on local inventory.db",
    )
    parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Extra args passed to pytest (e.g. -k epc)",
    )
    args = parser.parse_args()

    paths = ["tests"] if args.full else DEFAULT_PYTEST_PATHS
    code = run_pytest(paths, extra=args.pytest_args)
    if code != 0:
        return code

    if args.verify_seed:
        verify = subprocess.call([sys.executable, "scripts/verify_seed.py", "--strict"], cwd=ROOT)
        if verify != 0:
            return verify

    print("Smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
