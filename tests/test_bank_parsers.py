"""Per-bank credit-card statement parser tests (ported from CardQL)."""

from __future__ import annotations

from finance_common.parsing.bank_parsers import (
    axis_v1,
    hdfc_v1,
    hdfc_v2,
    hsbc_v1,
    icici_v1,
    indusind_v1,
    sbi_v1,
)
from finance_common.parsing.bank_parsers.registry import best_parse_for_bank, issuer_to_bank_slug


def test_axis_parses_debit_and_credit() -> None:
    text = (
        "14/02/2025 ZOMATO RESTAURANTS 547.59 Dr\n"
        "17/02/2025 BBPS PAYMENT RECEIVED REF 13.00 Cr\n"
    )
    rows = axis_v1.parse(text)
    assert len(rows) == 2
    assert rows[0]["date"] == "2025-02-14"
    assert rows[0]["amount"] == "547.59"
    assert rows[0]["transaction_type"] == "debit"
    assert rows[1]["transaction_type"] == "credit"


def test_axis_ignores_end_of_statement_and_header() -> None:
    text = "DATE TRANSACTION DETAILS MERCHANT CATEGORY AMOUNT\nEnd of Statement\n"
    assert axis_v1.parse(text) == []


def test_hdfc_v1_parses_within_domestic_transactions_section() -> None:
    text = (
        "Domestic Transactions\n"
        "15/02/2025 12:02:24 PAYTM UTILITY NOIDA 20.00\n"
        "25/02/2025 TATA 1MG HEALTHCARE SOLNEW DELHI 12.73 Cr\n"
        "Reward Points Summary\n"
        "01/03/2025 12:00:00 SHOULD NOT PARSE 99.00\n"
    )
    rows = hdfc_v1.parse(text)
    assert len(rows) == 2
    assert rows[0]["merchant"] == "PAYTM UTILITY NOIDA"
    assert rows[0]["transaction_type"] == "debit"
    assert rows[1]["transaction_type"] == "credit"


def test_hdfc_v2_distinguishes_debit_and_credit_tail() -> None:
    text = (
        "Domestic Transactions\n"
        "15/07/2025| 00:00 AMAZON PAY  C 19.80 l\n"
        "04/08/2025| 08:37 PAYMENT RECEIVED +  C 16,099.00 l\n"
    )
    rows = hdfc_v2.parse(text)
    assert len(rows) == 2
    assert rows[0]["amount"] == "19.80"
    assert rows[0]["transaction_type"] == "debit"
    assert rows[1]["amount"] == "16099.00"
    assert rows[1]["transaction_type"] == "credit"


def test_hsbc_extracts_smallest_plausible_amount() -> None:
    text = (
        "01 JAN 2026 To 31 JAN 2026\n"
        "PURCHASES & INSTALLMENTS\n"
        "13FEB SOME MERCHANT NAME 1,234.56\n"
        "TOTAL PURCHASE OUTSTANDING\n"
    )
    rows = hsbc_v1.parse(text)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-02-13"
    assert rows[0]["amount"] == "1234.56"
    assert rows[0]["transaction_type"] == "debit"


def test_icici_parses_serial_numbered_lines() -> None:
    text = (
        "Date SerNo Amount (in`)\n"
        "15/01/2026 12702848045 REPOVIVE, INC. COLLEGE PARK US 18 940.19\n"
        "29/01/2026 12776056934 BBPS Payment received 0 1,160.54 CR\n"
    )
    rows = icici_v1.parse(text)
    assert len(rows) == 2
    assert rows[0]["transaction_type"] == "debit"
    assert rows[1]["transaction_type"] == "credit"
    assert rows[1]["amount"] == "1160.54"


def test_indusind_requires_section_marker() -> None:
    text = (
        "Date Transaction Details Merchant Category Reward Points Amount (in )\n"
        "17/01/2026 DINING OUTLET GURGAON IN RESTAURANTS 21 1,043.00 DR\n"
        "Total 1 1,043.00\n"
        "18/01/2026 SHOULD NOT PARSE OUTSIDE SECTION 5 50.00 DR\n"
    )
    rows = indusind_v1.parse(text)
    assert len(rows) == 1
    assert rows[0]["amount"] == "1043.00"
    # Ported as-is from CardQL: the token immediately before the amount is the reward-points
    # count, not the merchant category, in this bank's line layout.
    assert rows[0]["notes"] == "IndusInd category: 21"


def test_sbi_dedupes_and_sorts() -> None:
    text = (
        "18 May 25 NETFLIX MUMBAI MAH 199.00 D\n"
        "18 May 25 NETFLIX MUMBAI MAH 199.00 D\n"
        "02 Jun 25 PAYMENT RECEIVED REF 5,744.34 C\n"
    )
    rows = sbi_v1.parse(text)
    assert len(rows) == 2  # duplicate line dropped
    assert rows[0]["date"] < rows[1]["date"]
    assert rows[1]["transaction_type"] == "credit"


def test_issuer_to_bank_slug() -> None:
    assert issuer_to_bank_slug("HDFC Bank") == "hdfc"
    assert issuer_to_bank_slug("State Bank of India") == "sbi"
    assert issuer_to_bank_slug("Axis Bank Ltd") == "axis"
    assert issuer_to_bank_slug(None) is None
    assert issuer_to_bank_slug("Some Unknown Co-op Bank") is None


def test_best_parse_for_bank_picks_higher_yield_variant() -> None:
    # hdfc_v2-shaped text: hdfc_v1 should yield 0, hdfc_v2 should yield 1.
    text = "Domestic Transactions\n15/07/2025| 00:00 AMAZON PAY  C 19.80 l\n"
    rows = best_parse_for_bank("hdfc", text)
    assert len(rows) == 1
    assert rows[0]["amount"] == "19.80"


def test_best_parse_for_bank_unknown_slug_returns_empty() -> None:
    assert best_parse_for_bank("unknown", "anything") == []
    assert best_parse_for_bank(None, "anything") == []
