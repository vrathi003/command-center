"""Process uploaded credit card statements (PDF / CSV / Excel)."""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from finance_api.services.transaction_import_service import MAX_BYTES, load_rows_from_upload
from finance_common.classification.matcher import ClassificationResult, match_merchant
from finance_common.parsing.bank_parsers.registry import best_parse_for_bank, issuer_to_bank_slug
from finance_common.parsing.bank_statement_pdf import (
    BankStatementPdfError,
    extract_text_from_pdf_bytes,
)
from finance_common.parsing.credit_card_statement import (
    import_rows_to_cc_line_items,
    infer_cc_payment_mode,
    line_items_from_tabular_rows,
    parse_credit_card_summary,
    truncate_preview,
)
from finance_common.repositories import merchant_rules as merchant_rules_repo

_SUPPORTED_BANKS_MSG = "Axis, HDFC, HSBC, ICICI, IndusInd, SBI"


async def build_credit_card_statement_payload(
    filename: str,
    content: bytes,
    *,
    pdf_password: str | None,
    issuer: str | None,
    conn: aiosqlite.Connection,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    """Return (summary dict, line_items, extraction_preview).

    PDFs are parsed with a dedicated per-bank parser keyed off the card's `issuer`
    (see `finance_common.parsing.bank_parsers`) — there is no generic heuristic/LLM
    fallback for credit-card statements; an unsupported or unrecognized bank layout is
    a clear upload error rather than a best-effort guess.
    """
    name = filename.lower().strip()
    if len(content) > MAX_BYTES:
        msg = f"file too large (max {MAX_BYTES // (1024 * 1024)} MB)"
        raise ValueError(msg)

    default_pm = infer_cc_payment_mode(issuer)
    rules = await merchant_rules_repo.list_active_rules_for_matching(conn)

    def classify(merchant: str) -> ClassificationResult:
        return match_merchant(merchant, rules)

    if name.endswith(".pdf"):
        pw = pdf_password.strip() if pdf_password else None
        try:
            text = extract_text_from_pdf_bytes(content, password=pw)
        except BankStatementPdfError as e:
            raise ValueError(str(e)) from e
        preview = truncate_preview(text)
        summary = parse_credit_card_summary(text)
        bank_slug = issuer_to_bank_slug(issuer)
        rows = best_parse_for_bank(bank_slug, text)
        if not rows:
            msg = (
                f"Could not parse this statement — no supported parser for issuer "
                f"{issuer!r}, or the statement layout wasn't recognized. "
                f"Supported banks: {_SUPPORTED_BANKS_MSG}."
            )
            raise ValueError(msg)
        lines = import_rows_to_cc_line_items(
            rows, default_payment_mode=default_pm, classify=classify
        )
        return summary, lines, preview

    if name.endswith((".csv", ".xlsx", ".xlsm")):
        raw_rows = load_rows_from_upload(filename, content)
        summary: dict[str, Any] = {}
        lines = line_items_from_tabular_rows(
            raw_rows, default_payment_mode=default_pm, classify=classify
        )
        return summary, lines, None

    raise ValueError("unsupported type — use .pdf, .csv, .xlsx, or .xlsm")


def dumps_summary(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False)


def dumps_line_items(items: list[dict[str, Any]]) -> str:
    return json.dumps(items, ensure_ascii=False)
