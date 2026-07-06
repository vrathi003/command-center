"""Gmail query helpers for statement import fetch window."""

from __future__ import annotations

from finance_api.services.statement_import_service import (
    build_gmail_query_for_rule,
    gmail_after_date,
    max_messages_for_fetch,
)


def test_gmail_after_date_uses_rolling_day() -> None:
    clause = gmail_after_date(3)
    parts = clause.split("/")
    assert len(parts) == 3
    assert int(parts[2]) >= 1


def test_max_messages_unlimited_when_zero() -> None:
    assert max_messages_for_fetch(0) == 50


def test_build_gmail_query_omits_after_when_unlimited() -> None:
    q = build_gmail_query_for_rule(["cc@bank.com"], "statement", fetch_months=0)
    assert "after:" not in q


def test_build_gmail_query_includes_after_clause() -> None:
    q = build_gmail_query_for_rule(
        ["cc@bank.com"],
        "statement",
        fetch_months=6,
    )
    assert "from:cc@bank.com" in q
    assert 'subject:"statement"' in q
    assert "has:attachment filename:pdf" in q
    assert q.endswith(gmail_after_date(6))


def test_max_messages_for_fetch_scales_with_months() -> None:
    assert max_messages_for_fetch(3) == 6
    assert max_messages_for_fetch(12) == 15
    assert max_messages_for_fetch(100) == 50
