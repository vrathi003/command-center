"""Statement import service unit tests."""

from __future__ import annotations

from finance_api.services.statement_import_service import (
    build_gmail_query_for_rule,
    transactions_to_csv,
)
from finance_common.parsing.statement_tags import compile_tag_rules, compute_tags


def test_build_gmail_query_single_from_and_subject() -> None:
    q = build_gmail_query_for_rule(
        ["credit_cards@icici.bank.in"],
        "icici bank credit card statement",
    )
    assert "from:credit_cards@icici.bank.in" in q
    assert 'subject:"icici bank credit card statement"' in q
    assert "has:attachment filename:pdf" in q


def test_build_gmail_query_multiple_from_emails() -> None:
    q = build_gmail_query_for_rule(
        ["a@bank.com", "b@bank.com"],
        None,
    )
    assert "(from:a@bank.com OR from:b@bank.com)" in q
    assert "subject:" not in q


def test_compute_tags_matches_description() -> None:
    rules = compile_tag_rules([("FOOD", ["zomato", "swiggy"])])
    assert compute_tags("ZOMATO ORDER 123", rules) == "FOOD"
    assert compute_tags("AMAZON IN", rules) == ""


def test_transactions_to_csv_header_and_row() -> None:
    csv_text = transactions_to_csv(
        [
            {
                "date": "2026-01-15",
                "bank": "ICICI",
                "card": "Card",
                "description": "TEST",
                "amount": 100.5,
                "currency": "INR",
                "category": "Other",
                "transaction_type": "debit",
                "tags": "FOOD",
                "statement_period": "2026-01",
                "gmail_message_id": "abc",
            }
        ]
    )
    assert "date,bank,card,description,amount" in csv_text.splitlines()[0]
    assert "2026-01-15,ICICI,Card,TEST,100.5" in csv_text
