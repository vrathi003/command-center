"""Process uploaded credit card statements (PDF / CSV / Excel)."""

from __future__ import annotations

import json
from typing import Any

from finance_api.services.transaction_import_service import MAX_BYTES, load_rows_from_upload
from finance_common.config import AppSettings
from finance_common.parsing.bank_statement_pdf import (
    BankStatementPdfError,
    extract_text_from_pdf_bytes,
    statement_text_to_import_rows,
)
from finance_common.parsing.credit_card_statement import (
    import_rows_to_cc_line_items,
    infer_cc_payment_mode,
    line_items_from_tabular_rows,
    parse_credit_card_summary,
    truncate_preview,
)


async def build_credit_card_statement_payload(
    filename: str,
    content: bytes,
    *,
    pdf_password: str | None,
    issuer: str | None,
    settings: AppSettings,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    """Return (summary dict, line_items, extraction_preview).

    PDFs use the same pipeline as bank-statement uploads: PyMuPDF text extraction, heuristic row
    parsing, then optional LM Studio when heuristics find no lines.
    """
    name = filename.lower().strip()
    if len(content) > MAX_BYTES:
        msg = f"file too large (max {MAX_BYTES // (1024 * 1024)} MB)"
        raise ValueError(msg)

    default_pm = infer_cc_payment_mode(issuer)

    if name.endswith(".pdf"):
        pw = pdf_password.strip() if pdf_password else None
        try:
            text = extract_text_from_pdf_bytes(content, password=pw)
        except BankStatementPdfError as e:
            raise ValueError(str(e)) from e
        preview = truncate_preview(text)
        summary = parse_credit_card_summary(text)
        try:
            rows = await statement_text_to_import_rows(text, settings)
        except BankStatementPdfError as e:
            raise ValueError(str(e)) from e
        lines = import_rows_to_cc_line_items(rows, default_payment_mode=default_pm)
        return summary, lines, preview

    if name.endswith((".csv", ".xlsx", ".xlsm")):
        raw_rows = load_rows_from_upload(filename, content)
        summary: dict[str, Any] = {}
        lines = line_items_from_tabular_rows(raw_rows, default_payment_mode=default_pm)
        return summary, lines, None

    raise ValueError("unsupported type — use .pdf, .csv, .xlsx, or .xlsm")


def dumps_summary(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False)


def dumps_line_items(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False)
