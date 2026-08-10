"""Credit card statement kind classification tests."""

from __future__ import annotations

from finance_common.parsing.credit_card_statement import (
    _classify_cc_description,
    import_rows_to_cc_line_items,
)


def test_classify_payment_vs_refund() -> None:
    pay = _classify_cc_description("BBPS Payment received")
    assert pay["kind"] == "payment"
    assert pay["skip"] is True

    refund = _classify_cc_description("AMAZON IN MERCHANT REFUND")
    assert refund["kind"] == "refund"
    assert refund["skip"] is False


def test_include_payments_shows_bill_paid_lines() -> None:
    rows = [
        {
            "date": "2026-01-29",
            "amount": "1160.54",
            "category": "Other",
            "merchant": "BBPS Payment received",
            "transaction_type": "credit",
        },
        {
            "date": "2026-01-15",
            "amount": "940.19",
            "category": "Other",
            "merchant": "ZOMATO",
            "transaction_type": "debit",
        },
    ]
    without = import_rows_to_cc_line_items(rows, default_payment_mode="ICICI CC")
    assert len(without) == 1
    assert without[0]["tx_kind"] == "spend"

    with_pay = import_rows_to_cc_line_items(
        rows, default_payment_mode="ICICI CC", include_payments=True
    )
    assert len(with_pay) == 2
    kinds = {x["tx_kind"] for x in with_pay}
    assert kinds == {"payment", "spend"}
