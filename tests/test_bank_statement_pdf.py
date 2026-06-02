"""Tests for PDF bank statement parsing (normalization, JSON, dedupe, mocked LLM)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from finance_common.config import AppSettings
from finance_common.parsing.bank_statement_pdf import (
    BankStatementPdfError,
    chunk_statement_text,
    dedupe_import_rows,
    filter_trailing_boilerplate_pages,
    normalize_llm_transaction_row,
    parse_json_object_from_model_text,
    pdf_bytes_to_import_rows,
)


def test_parse_json_object_from_model_text_fenced() -> None:
    raw = """```json
{"transactions": [], "meta": "ignored"}
```"""
    data = parse_json_object_from_model_text(raw)
    assert data["transactions"] == []


def test_parse_json_object_after_thinking_process_prefix() -> None:
    tx = (
        '{"date": "2025-01-01", "amount_inr": 10.0, "is_debit": true, '
        '"narration": "x", "merchant": null, "category": "Other", '
        '"payment_mode": "UPI", "notes": null}'
    )
    raw = f"""Thinking Process:

1. **Analyze the Request:** The user wants JSON.

{{"transactions": [{tx}]}}
"""
    data = parse_json_object_from_model_text(raw)
    assert len(data["transactions"]) == 1
    assert data["transactions"][0]["date"] == "2025-01-01"


def test_filter_trailing_boilerplate_pages() -> None:
    text = """--- Page 1 ---
2025-01-01  UPI A  100.00 Dr
--- Page 2 ---
2025-01-02  UPI B  200.00 Dr
--- Page 3 ---
Terms and Conditions. Privacy policy. Customer care.
"""
    out = filter_trailing_boilerplate_pages(text)
    assert "Terms and Conditions" not in out
    assert "2025-01-01" in out
    assert "2025-01-02" in out


def test_normalize_llm_transaction_row() -> None:
    r = normalize_llm_transaction_row(
        {
            "date": "2025-01-15",
            "amount_inr": 99.5,
            "is_debit": True,
            "narration": "UPI SOME MERCHANT",
            "merchant": "Some Merchant",
            "category": "Other",
            "payment_mode": "UPI",
            "notes": None,
        },
    )
    assert r["date"] == "2025-01-15"
    assert r["amount"] == "99.50"
    assert r["category"] == "Other"
    assert r["payment_mode"] == "UPI"
    assert r["merchant"] == "Some Merchant"


def test_dedupe_import_rows() -> None:
    row = {
        "date": "2025-01-01",
        "amount": "100.00",
        "category": "Other",
        "payment_mode": "UPI",
        "merchant": "same",
    }
    assert len(dedupe_import_rows([row, row])) == 1


def test_chunk_statement_text_splits() -> None:
    text = "x" * 100
    chunks = chunk_statement_text(text, max_chars=30, overlap=5)
    assert len(chunks) >= 2


@pytest.mark.asyncio
async def test_pdf_bytes_to_import_rows_uses_heuristic_without_llm() -> None:
    """PyMuPDF text + heuristic lines must not call LM Studio when lines match."""
    settings = AppSettings.model_construct(
        lm_studio_enabled=False,
        lm_studio_url="http://127.0.0.1:1234/v1",
        lm_studio_model="test",
        db_path=Path("/tmp/finance-test.db"),
        app_env="test",
        log_level="INFO",
    )
    text = "2025-01-15  UPI MERCHANT  500.00 Dr\n"
    with (
        patch(
            "finance_common.parsing.bank_statement_pdf.extract_text_from_pdf_bytes",
            return_value=text,
        ),
        patch(
            "finance_common.parsing.bank_statement_pdf._call_llm_for_chunk",
            new_callable=AsyncMock,
        ) as m_llm,
    ):
        rows = await pdf_bytes_to_import_rows(b"%PDF-fake", settings)
    m_llm.assert_not_called()
    assert len(rows) == 1
    assert rows[0]["amount"] == "500.00"


@pytest.mark.asyncio
async def test_pdf_bytes_to_import_rows_skips_llm_when_disabled() -> None:
    """When LM_STUDIO_ENABLED=false, heuristic failure must not call LM Studio."""
    settings = AppSettings.model_construct(
        lm_studio_enabled=False,
        lm_studio_url="http://127.0.0.1:1234/v1",
        lm_studio_model="test",
        db_path=Path("/tmp/finance-test.db"),
        app_env="test",
        log_level="INFO",
    )
    with (
        patch(
            "finance_common.parsing.bank_statement_pdf.extract_text_from_pdf_bytes",
            return_value="--- Page 1 ---\nunparseable blob",
        ),
        patch(
            "finance_common.parsing.bank_statement_pdf.heuristic_rows_from_statement_text",
            return_value=[],
        ),
        patch(
            "finance_common.parsing.bank_statement_pdf._call_llm_for_chunk",
            new_callable=AsyncMock,
        ) as m_llm,
    ):
        with pytest.raises(BankStatementPdfError, match="Heuristic parsing found no transaction lines"):
            await pdf_bytes_to_import_rows(b"%PDF-fake", settings)
    m_llm.assert_not_called()


@pytest.mark.asyncio
async def test_pdf_bytes_to_import_rows_mocked_llm() -> None:
    settings = AppSettings()
    settings.lm_studio_url = "http://127.0.0.1:1234/v1"
    settings.lm_studio_model = "test-model"
    fake_tx = {
        "date": "2025-01-01",
        "amount_inr": 100,
        "is_debit": True,
        "narration": "test",
        "merchant": "m",
        "category": "Other",
        "payment_mode": "UPI",
        "notes": None,
    }
    with (
        patch(
            "finance_common.parsing.bank_statement_pdf.extract_text_from_pdf_bytes",
            return_value="--- Page 1 ---\nstatement line",
        ),
        patch(
            "finance_common.parsing.bank_statement_pdf._call_llm_for_chunk",
            new_callable=AsyncMock,
            return_value=[fake_tx],
        ),
    ):
        rows = await pdf_bytes_to_import_rows(b"%PDF-fake", settings)
    assert len(rows) == 1
    assert rows[0]["date"] == "2025-01-01"
    assert rows[0]["amount"] == "100.00"
