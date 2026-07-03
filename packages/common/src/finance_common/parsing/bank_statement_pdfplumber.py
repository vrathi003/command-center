"""pdfplumber-based table extraction for Indian bank / CC statement PDFs.

Used as the primary extraction layer before falling back to heuristic line-regex
parsing (``bank_statement_text_heuristic``) and LM Studio / Ollama.

pdfplumber understands PDF table structure spatially, so it correctly handles the
multi-column layouts common in Indian CC statements (HDFC, ICICI, Axis, SBI, etc.)
where PyMuPDF text extraction scrambles the columns into single joined lines that
defeat line-by-line regex.
"""

from __future__ import annotations

import io
import re
from datetime import datetime

from finance_common.parsing.import_column_mapping import (
    build_canonical_import_row,
    normalize_header_key,
    resolve_column_role,
    score_header_row,
)

# Indian bank / CC statements use these date formats beyond the ISO standard.
_EXTENDED_DATE_FMTS = (
    "%d %b %y",   # 15 Jun 24
    "%d %b %Y",   # 15 Jun 2024
    "%d-%b-%y",   # 15-Jun-24
    "%d-%b-%Y",   # 15-Jun-2024
    "%d/%b/%y",   # 15/Jun/24
    "%d/%b/%Y",   # 15/Jun/2024
    "%d.%m.%Y",   # 15.06.2024
    "%d.%m.%y",   # 15.06.24
    "%b %d, %Y",  # Jun 15, 2024
)

_STANDARD_DATE_FMTS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y/%m/%d",
)


def _try_parse_date(s: str) -> str | None:
    """Return YYYY-MM-DD or None; handles Indian CC statement date formats."""
    t = s.strip()
    if not t:
        return None
    # Standard formats (first 10 chars suffice)
    for fmt in _STANDARD_DATE_FMTS:
        try:
            return datetime.strptime(t[:10], fmt).date().isoformat()
        except ValueError:
            continue
    # Extended month-name formats (need full string)
    for fmt in _EXTENDED_DATE_FMTS:
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_amount(val: str) -> str | None:
    """Strip currency symbols/commas and return string float, or None."""
    t = re.sub(r"[₹,\s]", "", val.strip())
    if not t:
        return None
    try:
        x = float(t)
        return f"{x:.2f}" if x > 0 else None
    except ValueError:
        return None


# Matches "Dr/Cr", "DR/CR", "Debit/Credit", "Dr.", "Type" columns that signal direction.
_DRCR_HEADER_RE = re.compile(r"dr[/\-.]?cr|debit[/.]credit|d/c", re.IGNORECASE)
_DR_VAL_RE = re.compile(r"\bdr\b|\bdebit\b|\bdebited\b", re.IGNORECASE)
_CR_VAL_RE = re.compile(r"\bcr\b|\bcredit\b|\bcredited\b", re.IGNORECASE)


def _is_drcr_header(cell: str) -> bool:
    return bool(_DRCR_HEADER_RE.search(cell))


def _classify_drcr_val(val: str) -> str | None:
    """Return 'debit' or 'credit' from a Dr/Cr indicator cell, or None."""
    v = val.strip()
    if _DR_VAL_RE.search(v):
        return "debit"
    if _CR_VAL_RE.search(v):
        return "credit"
    return None


def _is_trailer_cell(val: str) -> bool:
    """True if a row looks like a summary/totals row rather than a real transaction."""
    low = val.lower()
    return any(
        kw in low
        for kw in (
            "total", "subtotal", "grand total",
            "opening balance", "closing balance", "brought forward",
        )
    )


def _table_to_rows(table: list[list[str | None]]) -> list[dict[str, str]]:
    """Convert one pdfplumber table to canonical import row dicts."""
    if not table or len(table) < 2:
        return []

    # Find header row (scan first 4 rows).
    header_idx: int | None = None
    for i in range(min(4, len(table))):
        cells = [str(c or "").strip() for c in table[i]]
        score, has_date = score_header_row(cells)
        if score >= 2 and has_date:
            header_idx = i
            break

    if header_idx is None:
        return []

    header_cells = [str(c or "").strip() for c in table[header_idx]]

    # Identify the Dr/Cr indicator column (if present).
    drcr_col: int | None = None
    for j, cell in enumerate(header_cells):
        if _is_drcr_header(cell):
            drcr_col = j
            break

    # Identify the date column index (for extended date parsing fallback).
    date_col: int | None = None
    for j, cell in enumerate(header_cells):
        nk = normalize_header_key(cell)
        if resolve_column_role(nk) == "date":
            date_col = j
            break

    rows: list[dict[str, str]] = []
    for row in table[header_idx + 1:]:
        if not row:
            continue
        cells = [str(c or "").strip() for c in row]
        if not any(cells):
            continue

        # Skip totals/summary rows.
        if cells[0] and _is_trailer_cell(cells[0]):
            continue

        # Build raw dict: original header text → cell value.
        raw: dict[str, str] = {}
        for j, header in enumerate(header_cells):
            if j < len(cells) and cells[j] and header:
                raw[header] = cells[j]

        canonical = build_canonical_import_row(raw)

        # Extended date parsing: build_canonical_import_row stores raw date text;
        # try to parse it into YYYY-MM-DD for the downstream pipeline.
        if "date" in canonical:
            iso = _try_parse_date(canonical["date"])
            if iso:
                canonical["date"] = iso
            else:
                canonical.pop("date")  # unparseable — skip below

        # If date missing, fall back to direct cell lookup.
        if "date" not in canonical and date_col is not None and date_col < len(cells):
            iso = _try_parse_date(cells[date_col])
            if iso:
                canonical["date"] = iso

        # Amount: build_canonical_import_row should handle debit/credit split columns
        # already; but CC amount cells with "₹" prefix need stripping.
        if "amount" in canonical:
            fixed = _normalize_amount(canonical["amount"])
            if fixed:
                canonical["amount"] = fixed
            else:
                canonical.pop("amount")

        if not canonical.get("date") or not canonical.get("amount"):
            continue

        # Apply Dr/Cr type column override if found.
        if drcr_col is not None and drcr_col < len(cells):
            tx_type = _classify_drcr_val(cells[drcr_col])
            if tx_type:
                canonical["transaction_type"] = tx_type

        # Ensure a sensible default category.
        if "category" not in canonical:
            canonical["category"] = "Other"

        rows.append(canonical)
    return rows


def extract_rows_via_pdfplumber(
    pdf_bytes: bytes,
    password: str | None = None,
) -> list[dict[str, str]]:
    """Return canonical import rows extracted from PDF tables using pdfplumber.

    Returns an empty list (not an error) when pdfplumber is not installed or the
    PDF contains no recognisable transaction tables — callers fall through to the
    heuristic / LLM pipeline.
    """
    try:
        import pdfplumber
    except ImportError:
        return []

    rows: list[dict[str, str]] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes), password=password) as pdf:
            for page in pdf.pages:
                try:
                    tables = page.extract_tables()
                except Exception:
                    continue
                for table in tables:
                    rows.extend(_table_to_rows(table))
    except Exception:
        return []

    # Deduplicate (same date + amount + merchant from overlapping page detection).
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for r in rows:
        key = (
            r.get("date", ""),
            r.get("amount", ""),
            (r.get("merchant") or r.get("notes") or "")[:80],
        )
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped
