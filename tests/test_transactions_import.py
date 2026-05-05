"""Transaction file import API tests."""

from __future__ import annotations

from io import BytesIO

import pytest
from starlette.testclient import TestClient

from finance_common.parsing.transaction_import import (
    categorize_from_merchant,
    detect_header_row,
    extract_merchant_from_narration,
    trim_trailer_rows,
)


def test_import_transactions_csv(api_client: TestClient) -> None:
    csv_content = (
        "date,amount,category,merchant,payment_mode\n"
        "2025-06-15,1500.50,Groceries,BigBasket,UPI\n"
        "2025-06-16,99,Other,,cash\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("txns.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2
    assert body["failed"] == 0
    assert body["errors"] == []

    lst = api_client.get("/api/transactions/?limit=10")
    assert lst.status_code == 200
    rows = lst.json()
    assert len(rows) >= 2
    sources = {x["source"] for x in rows[:2]}
    assert "import" in sources

    ids = [x["id"] for x in rows if x["source"] == "import"]
    assert len(ids) >= 2
    r_del = api_client.post("/api/transactions/bulk-delete", json={"ids": ids[:2]})
    assert r_del.status_code == 200
    assert r_del.json()["deleted"] == 2

    lst2 = api_client.get("/api/transactions/?limit=50")
    assert lst2.status_code == 200
    remaining_ids = {x["id"] for x in lst2.json()}
    assert ids[0] not in remaining_ids
    assert ids[1] not in remaining_ids


def test_import_transactions_rejects_bad_extension(api_client: TestClient) -> None:
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("bad.txt", BytesIO(b"x"), "text/plain")},
    )
    assert r.status_code == 400


def test_import_transactions_bank_debit_credit_without_category(api_client: TestClient) -> None:
    """HDFC-style: date + particulars + separate Debit/Credit; category column optional."""
    csv_content = (
        "Booking Date,Particulars,Debit,Credit\n"
        "2025-06-15,UPI merchant,1500.50,\n"
        "2025-06-16,Salary credit,,2500.00\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("stmt.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2
    assert body["failed"] == 0


def test_import_transactions_rejects_non_xlsx_content(api_client: TestClient) -> None:
    """.xlsx must be OOXML (zip); CSV renamed or .xls mislabeled raises 400 with a clear message."""
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("fake.xlsx", BytesIO(b"date,amount,category\n"), "application/octet-stream")},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "PK" in detail or "valid" in detail.lower()


# --- Bank statement header detection unit tests ---


class TestDetectHeaderRow:
    def test_header_on_row_zero(self) -> None:
        rows = [
            ["Date", "Narration", "Debit", "Credit", "Balance"],
            ["15/06/2025", "UPI-BIGBASKET", "1500.50", "", "45000"],
        ]
        assert detect_header_row(rows) == 0

    def test_header_after_preamble(self) -> None:
        rows = [
            ["HDFC BANK LTD", "", "", "", ""],
            ["Account No: XXXX1234", "", "", "", ""],
            ["Statement from 01/06/2025 to 30/06/2025", "", "", "", ""],
            ["", "", "", "", ""],
            ["Date", "Narration", "Debit", "Credit", "Closing Balance"],
            ["15/06/2025", "UPI-BIGBASKET", "1500.50", "", "45000"],
        ]
        assert detect_header_row(rows) == 4

    def test_sbi_style_preamble(self) -> None:
        rows = [
            ["STATE BANK OF INDIA", "", "", ""],
            ["Branch: KORAMANGALA", "", "", ""],
            ["A/c No: 123456789", "", "", ""],
            ["Txn Date", "Description", "Withdrawal", "Deposit"],
            ["2025-06-15", "UPI/123456", "500", ""],
        ]
        assert detect_header_row(rows) == 3

    def test_no_date_column_returns_none(self) -> None:
        rows = [
            ["Name", "Amount", "Category"],
            ["Foo", "100", "Food"],
        ]
        # "Amount" and "Category" match, but no date column -> None
        assert detect_header_row(rows) is None

    def test_single_column_returns_none(self) -> None:
        rows = [["Date"], ["2025-01-01"]]
        # Only 1 known header (need >= 2)
        assert detect_header_row(rows) is None

    def test_picks_highest_scoring_row(self) -> None:
        rows = [
            ["Date", "Amount"],  # score 2
            ["", "", ""],
            ["Date", "Narration", "Debit", "Credit", "Balance"],  # score 5
        ]
        assert detect_header_row(rows) == 2

    def test_empty_rows(self) -> None:
        assert detect_header_row([]) is None
        assert detect_header_row([["", ""]]) is None


class TestTrimTrailerRows:
    def test_removes_trailing_blank_date_rows(self) -> None:
        rows = [
            {"Date": "2025-06-15", "Amount": "100"},
            {"Date": "2025-06-16", "Amount": "200"},
            {"Date": "", "Amount": ""},
            {"Date": "", "Amount": "Total: 300"},
        ]
        result = trim_trailer_rows(rows)
        assert len(result) == 2

    def test_removes_total_keyword_rows(self) -> None:
        rows = [
            {"Date": "2025-06-15", "Amount": "100"},
            {"Date": "Total", "Amount": "100"},
        ]
        result = trim_trailer_rows(rows)
        assert len(result) == 1

    def test_removes_statement_generated_row(self) -> None:
        rows = [
            {"Booking Date": "2025-06-15", "Amount": "100"},
            {"Booking Date": "Statement generated on 25/03/2026", "Amount": ""},
        ]
        result = trim_trailer_rows(rows)
        assert len(result) == 1

    def test_preserves_all_valid_rows(self) -> None:
        rows = [
            {"Date": "2025-06-15", "Amount": "100"},
            {"Date": "2025-06-16", "Amount": "200"},
        ]
        result = trim_trailer_rows(rows)
        assert len(result) == 2

    def test_empty_input(self) -> None:
        assert trim_trailer_rows([]) == []


# --- End-to-end bank statement CSV import tests ---


def test_import_csv_with_bank_preamble(api_client: TestClient) -> None:
    """HDFC-style CSV: preamble rows before the actual header row."""
    csv_content = (
        "HDFC BANK LTD,,,,\n"
        "Account No: XXXX1234,,,,\n"
        "Statement from 01/06/2025 to 30/06/2025,,,,\n"
        ",,,,\n"
        "Date,Narration,Debit,Credit,Closing Balance\n"
        "15/06/2025,UPI-BIGBASKET,1500.50,,45000\n"
        "16/06/2025,NEFT-SALARY,,25000,70000\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("hdfc_stmt.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2
    assert body["failed"] == 0


def test_import_csv_with_trailer_rows(api_client: TestClient) -> None:
    """CSV with summary/total rows at the bottom that should be ignored."""
    csv_content = (
        "Date,Particulars,Debit,Credit\n"
        "15/06/2025,UPI-SWIGGY,350,\n"
        "16/06/2025,ATM WITHDRAWAL,2000,\n"
        ",,,\n"
        "Total,,2350,0\n"
        "Statement generated on 25/03/2026,,,\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("stmt.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2
    assert body["failed"] == 0


# --- Debit/credit detection and auto-categorization tests ---


def test_import_debit_credit_type_detected(api_client: TestClient) -> None:
    """Separate Debit/Credit columns should set transaction_type correctly."""
    csv_content = (
        "Date,Details,Debit,Credit\n"
        "2025-06-15,UPI/Zomato Ltd,345.69,\n"
        "2025-06-16,NEFT-SALARY,,25000\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("stmt.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 2

    txns = api_client.get("/api/transactions/?limit=10").json()
    imported = [t for t in txns if t["source"] == "import"]
    zomato = [t for t in imported if t["merchant"] and "Zomato" in t["merchant"]]
    salary = [t for t in imported if t["merchant"] and "SALARY" in t["merchant"]]
    if zomato:
        assert zomato[0]["transaction_type"] == "debit"
    if salary:
        assert salary[0]["transaction_type"] == "credit"


def test_import_details_column_maps_to_merchant(api_client: TestClient) -> None:
    """The 'Details' column should map to merchant field."""
    csv_content = (
        "Date,Details,Debit,Credit\n"
        "2025-06-15,WDL TFR UPI/DR/Zomato,370.20,\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("stmt.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 1

    txns = api_client.get("/api/transactions/?limit=5").json()
    imported = [t for t in txns if t["source"] == "import" and t["merchant"]]
    assert any("Zomato" in (t["merchant"] or "") for t in imported)


def test_extract_merchant_from_narration_upi_hdfc() -> None:
    s = (
        "WDL TFR UPI/DR/102786697305/APPLE ME/HDFC/app leservi/Exec 0097693162093 "
        "AT 00738 MODINAGAR"
    )
    assert extract_merchant_from_narration(s) == "APPLE ME"


def test_extract_merchant_from_narration_upi_person() -> None:
    assert extract_merchant_from_narration("UPI/DR/204516359314/SURAJ KU") == "SURAJ KU"


def test_extract_merchant_from_narration_standalone_brand() -> None:
    assert extract_merchant_from_narration("CREDITSAISON") == "CREDITSAISON"


def test_extract_merchant_from_narration_no_ref_segment() -> None:
    assert extract_merchant_from_narration("UPI/DR/Zomato Ltd/YESBANK") == "Zomato Ltd"


def test_auto_categorize_from_merchant() -> None:
    """categorize_from_merchant should match known keywords."""
    assert categorize_from_merchant("UPI/DR/Zomato Ltd/YESB") == "Food Delivery"
    assert categorize_from_merchant("BIGBASKET order") == "Groceries"
    assert categorize_from_merchant("NEFT SALARY") is None
    assert categorize_from_merchant(None) is None
    assert categorize_from_merchant("Uber trip") == "Transport & Fuel"


def test_import_auto_categorizes_zomato(api_client: TestClient) -> None:
    """Zomato in merchant should auto-categorize as Food Delivery."""
    csv_content = (
        "Date,Narration,Debit,Credit\n"
        "2025-06-15,UPI/Zomato Ltd/YESB,345.69,\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("stmt.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 1

    txns = api_client.get("/api/transactions/?limit=5").json()
    imported = [t for t in txns if t["source"] == "import" and t["merchant"] and "Zomato" in t["merchant"]]
    assert len(imported) >= 1
    assert imported[0]["category"] == "Food Delivery"


def test_list_transactions_date_filter(api_client: TestClient) -> None:
    """API should support start_date/end_date query params."""
    csv_content = (
        "date,amount,category\n"
        "2024-01-15,100,Other\n"
        "2025-06-15,200,Other\n"
    )
    r = api_client.post(
        "/api/transactions/import",
        files={"file": ("txns.csv", BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert r.status_code == 200

    filtered = api_client.get("/api/transactions/?limit=100&start_date=2024-01-01&end_date=2024-12-31")
    assert filtered.status_code == 200
    rows = filtered.json()
    dates = [t["date"] for t in rows]
    assert all(d.startswith("2024") for d in dates)
