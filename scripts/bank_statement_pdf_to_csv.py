"""Convert a bank statement PDF to CSV using local LLM inference (see LOCAL_LLM_URL in `.env`).

Usage (from repo root):
  uv run python scripts/bank_statement_pdf_to_csv.py statement.pdf -o out.csv

Does not require the API server; only LM Studio with the configured model.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from finance_common.config import AppSettings
from finance_common.parsing.bank_statement_pdf import (
    BankStatementPdfError,
    pdf_bytes_to_import_rows,
)

_CSV_FIELDS = ("date", "amount", "category", "merchant", "payment_mode", "notes", "account")


async def _run(pdf_path: Path, out_path: Path, password: str | None) -> int:
    settings = AppSettings()
    pdf_bytes = pdf_path.read_bytes()
    try:
        rows = await pdf_bytes_to_import_rows(pdf_bytes, settings, password=password)
    except BankStatementPdfError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if not rows:
        print("No transactions extracted.", file=sys.stderr)
        return 2
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(_CSV_FIELDS), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _CSV_FIELDS})
    print(f"Wrote {len(rows)} row(s) to {out_path}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="PDF bank statement → CSV via LM Studio")
    p.add_argument("pdf", type=Path, help="Path to the bank statement PDF")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output CSV path",
    )
    p.add_argument(
        "-p",
        "--password",
        default=None,
        help="PDF password if the file is encrypted",
    )
    args = p.parse_args()
    if not args.pdf.is_file():
        print(f"Not a file: {args.pdf}", file=sys.stderr)
        sys.exit(1)
    code = asyncio.run(_run(args.pdf, args.output, args.password))
    sys.exit(code)


if __name__ == "__main__":
    main()
