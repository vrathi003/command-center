"""Excel → SQLite migration (Phase 6 in spec). Placeholder CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


async def _run(args: argparse.Namespace) -> int:
    xlsx = Path(args.xlsx).expanduser().resolve()
    db = Path(args.db).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve() if args.report else None

    if not xlsx.exists():
        print(f"Excel file not found: {xlsx}", file=sys.stderr)
        return 1

    # Import deferred until pandas/openpyxl are added for real migration.
    report = {
        "status": "not_implemented",
        "xlsx": str(xlsx),
        "db": str(db),
        "dry_run": args.dry_run,
        "message": (
            "Wire pandas + sheet mapping per spec section 10; "
            "use finance_common.db.ensure_database first."
        ),
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {report_path}")
    else:
        print(json.dumps(report, indent=2))
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="Migrate Personal Finance OS Excel into SQLite.")
    p.add_argument("--xlsx", required=True, help="Path to .xlsx export")
    p.add_argument("--db", required=True, help="Target SQLite path (e.g. ~/finance/finance.db)")
    p.add_argument("--report", default="migration_report.json", help="JSON report output path")
    p.add_argument("--dry-run", action="store_true", help="Parse only; no DB writes")
    args = p.parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
