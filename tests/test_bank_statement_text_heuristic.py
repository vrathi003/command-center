"""Heuristic bank statement line parsing (no LLM)."""

from __future__ import annotations

from finance_common.parsing.bank_statement_text_heuristic import heuristic_rows_from_statement_text


def test_heuristic_iso_date_dr() -> None:
    text = "2025-01-15  UPI MERCHANT  500.00 Dr\n"
    rows = heuristic_rows_from_statement_text(text)
    assert len(rows) == 1
    assert rows[0]["date"] == "2025-01-15"
    assert rows[0]["amount"] == "500.00"
    assert rows[0]["payment_mode"] == "UPI"


def test_heuristic_dmy_credit() -> None:
    text = "15/01/2025  NEFT SALARY  25000.00 Cr\n"
    rows = heuristic_rows_from_statement_text(text)
    assert len(rows) == 1
    assert rows[0]["date"] == "2025-01-15"
    assert rows[0]["amount"] == "25000.00"
    assert rows[0]["category"] == "Income"
