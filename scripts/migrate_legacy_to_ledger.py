"""Migrate legacy `transactions` rows into the double-entry ledger.

Usage:
  uv run python scripts/migrate_legacy_to_ledger.py --dry-run
  uv run python scripts/migrate_legacy_to_ledger.py --apply

Requires DB_PATH in .env (see .env.example). Prints a MigrationReport JSON object to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict

from finance_common.config import AppSettings
from finance_common.db import ensure_database, open_db
from finance_common.migration.service import apply, dry_run


async def _run(*, dry_run_mode: bool) -> int:
    settings = AppSettings()
    await ensure_database(settings.db_path)
    async with open_db(settings.db_path) as conn:
        if dry_run_mode:
            report = await dry_run(conn)
        else:
            report = await apply(conn, db_path=settings.db_path)
    print(json.dumps(asdict(report), indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy transactions into the double-entry ledger.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan migration and print counts without writing to the database.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Back up the database, migrate legacy rows, archive, and mark cutover.",
    )
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(_run(dry_run_mode=args.dry_run)))
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
