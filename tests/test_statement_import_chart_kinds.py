"""Tests for statement import chart kind resolution (refund offset logic)."""

from finance_common.parsing.statement_import_chart_kinds import aggregate_chart_kinds_by_type


def _row(
    *,
    id: str,
    amount: float,
    tx_kind: str = "spend",
    bank: str = "ICICI",
    card: str = "ICICI Credit Card",
    date: str = "2026-01-15",
    statement_period: str = "2026-01",
) -> dict:
    return {
        "id": id,
        "amount": amount,
        "tx_kind": tx_kind,
        "bank": bank,
        "card": card,
        "date": date,
        "statement_period": statement_period,
    }


def test_matched_refund_offsets_spend() -> None:
    rows = [
        _row(id="s1", amount=999.0, tx_kind="spend"),
        _row(id="r1", amount=999.0, tx_kind="refund", date="2026-01-20"),
    ]
    sums = aggregate_chart_kinds_by_type(rows)
    assert "spend" not in sums
    assert "refund" not in sums
    assert "payment" not in sums


def test_refund_within_discount_tolerance_offsets_spend() -> None:
    rows = [
        _row(id="s1", amount=1000.0, tx_kind="spend"),
        _row(id="r1", amount=988.0, tx_kind="refund", date="2026-01-20"),
    ]
    sums = aggregate_chart_kinds_by_type(rows)
    assert "spend" not in sums
    assert "payment" not in sums


def test_unmatched_refund_counts_as_payment() -> None:
    rows = [
        _row(id="r1", amount=5000.0, tx_kind="refund"),
    ]
    sums = aggregate_chart_kinds_by_type(rows)
    assert sums["payment"]["count"] == 1
    assert sums["payment"]["amount"] == 5000.0
    assert "refund" not in sums


def test_refund_never_appears_in_chart_sums() -> None:
    rows = [
        _row(id="s1", amount=500.0, tx_kind="spend"),
        _row(id="r1", amount=200.0, tx_kind="refund", date="2026-01-20"),
    ]
    sums = aggregate_chart_kinds_by_type(rows)
    assert "refund" not in sums
    assert sums["spend"]["amount"] == 500.0
    assert sums["payment"]["amount"] == 200.0
