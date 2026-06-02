"""Unit tests for bank CSV column header mapping."""

from __future__ import annotations

import pytest

from finance_common.parsing.import_column_mapping import (
    build_canonical_import_row,
    normalize_header_key,
    resolve_column_role,
)


class TestNormalizeHeaderKey:
    def test_inr_suffix_stripped(self) -> None:
        assert normalize_header_key("Withdrawal Amount(INR)") == "withdrawal_amount"
        assert normalize_header_key("Deposit Amount(INR)") == "deposit_amount"

    def test_bom_and_spaces(self) -> None:
        assert normalize_header_key("\ufeffValue Date") == "value_date"


class TestResolveColumnRole:
    @pytest.mark.parametrize(
        ("header", "role"),
        [
            ("Value Date", "date"),
            ("Transaction Date", "date"),
            ("Booking Date", "date"),
            ("Txn Date", "date"),
            ("Withdrawal Amount(INR)", "debit"),
            ("Deposit Amount(INR)", "credit"),
            ("Transaction Remarks", "merchant"),
            ("Particulars", "merchant"),
            ("Debit", "debit"),
            ("Credit", "credit"),
            ("Withdrawal", "debit"),
            ("Deposit", "credit"),
            ("Balance(INR)", "meta"),
            ("S No.", "meta"),
        ],
    )
    def test_known_bank_headers(self, header: str, role: str) -> None:
        assert resolve_column_role(normalize_header_key(header)) == role

    def test_unknown_bank_withdrawal_substring(self) -> None:
        """New bank uses non-standard label but contains 'withdrawal'."""
        assert resolve_column_role(normalize_header_key("Total Withdrawal Amt")) == "debit"

    def test_unknown_bank_money_in(self) -> None:
        assert resolve_column_role(normalize_header_key("Money In")) == "credit"


class TestBuildCanonicalImportRow:
    def test_hdfc_inr_export(self) -> None:
        raw = {
            "Value Date": "15/06/2025",
            "Transaction Date": "14/06/2025",
            "Transaction Remarks": "UPI-BIGBASKET",
            "Withdrawal Amount(INR)": "1500.50",
            "Deposit Amount(INR)": "",
        }
        canon = build_canonical_import_row(raw)
        assert canon["date"] == "15/06/2025"
        assert canon["amount"] == "1500.50"
        assert canon["merchant"] == "UPI-BIGBASKET"
        assert canon["transaction_type"] == "debit"

    def test_hdfc_booking_debit_credit(self) -> None:
        raw = {
            "Booking Date": "2025-06-15",
            "Particulars": "UPI merchant",
            "Debit": "1500.50",
            "Credit": "",
        }
        canon = build_canonical_import_row(raw)
        assert canon["date"] == "2025-06-15"
        assert canon["amount"] == "1500.50"
        assert canon["merchant"] == "UPI merchant"

    def test_sbi_withdrawal_deposit(self) -> None:
        raw = {
            "Txn Date": "2025-06-15",
            "Description": "UPI/123",
            "Withdrawal": "500",
            "Deposit": "",
        }
        canon = build_canonical_import_row(raw)
        assert canon["amount"] == "500"
        assert canon["transaction_type"] == "debit"

    def test_credit_only_row(self) -> None:
        raw = {
            "Date": "2025-06-16",
            "Narration": "Salary",
            "Debit": "",
            "Credit": "25000",
        }
        canon = build_canonical_import_row(raw)
        assert canon["amount"] == "25000"
        assert canon["transaction_type"] == "credit"

    def test_single_amount_column(self) -> None:
        raw = {"date": "2025-06-15", "amount": "99", "category": "Food"}
        canon = build_canonical_import_row(raw)
        assert canon["amount"] == "99"
        assert canon["category"] == "Food"
