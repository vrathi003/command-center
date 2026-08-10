"""Double-entry approval tests for staged Gmail transactions."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _seed_accounts() -> dict[str, int]:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    accounts = [
        ("Bank", "savings", "asset_cash"),
        ("Bank 2", "savings", "asset_cash"),
        ("Uncategorized Expense", "expense", "expense"),
        ("Uncategorized Income", "income", "income"),
    ]
    conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    conn.commit()
    rows = conn.execute("SELECT id, name FROM accounts").fetchall()
    conn.close()
    return {name: account_id for account_id, name in rows}


def _stage(
    *,
    gmail_message_id: str,
    account_id: int,
    tx_type: str = "debit",
    amount_paise: int = 12_500,
    parsed_date: str = "2026-08-01",
    merchant: str = "Coffee Shop",
) -> int:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    cursor = conn.execute(
        """
        INSERT INTO email_transaction_staging (
            gmail_message_id, email_date, parsed_date, parsed_amount_paise,
            parsed_merchant, parsed_category, parsed_payment_mode,
            parsed_transaction_type, suggested_account_id
        ) VALUES (?, ?, ?, ?, ?, 'Food', 'UPI', ?, ?)
        """,
        (
            gmail_message_id,
            parsed_date,
            parsed_date,
            amount_paise,
            merchant,
            tx_type,
            account_id,
        ),
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    assert item_id is not None
    return int(item_id)


def _ledger_status(transaction_id: int) -> str:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    row = conn.execute(
        "SELECT status FROM ledger_transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    return str(row[0])


def test_approve_staged_email_posts_ledger_transaction(api_client: TestClient) -> None:
    ids = _seed_accounts()
    item_id = _stage(gmail_message_id="approve-1", account_id=ids["Bank"])

    response = api_client.post(f"/api/email-inbox/{item_id}/approve", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["created_transaction_id"] is None
    ledger_transaction_id = body["ledger_transaction_id"]
    assert _ledger_status(ledger_transaction_id) == "posted"


def test_approve_blocks_soft_duplicate_unless_forced(api_client: TestClient) -> None:
    ids = _seed_accounts()
    first_item = _stage(gmail_message_id="duplicate-1", account_id=ids["Bank"])
    assert api_client.post(f"/api/email-inbox/{first_item}/approve", json={}).status_code == 200
    second_item = _stage(gmail_message_id="duplicate-2", account_id=ids["Bank"])

    duplicate = api_client.post(f"/api/email-inbox/{second_item}/approve", json={})
    assert duplicate.status_code == 409
    assert "duplicate" in duplicate.json()["detail"].lower()

    forced = api_client.post(f"/api/email-inbox/{second_item}/approve", json={"force": True})
    assert forced.status_code == 200
    assert forced.json()["ledger_transaction_id"] != 0


def test_undo_approved_email_voids_ledger_transaction(api_client: TestClient) -> None:
    ids = _seed_accounts()
    item_id = _stage(gmail_message_id="undo-1", account_id=ids["Bank"])
    approved = api_client.post(f"/api/email-inbox/{item_id}/approve", json={}).json()

    undone = api_client.delete(f"/api/email-inbox/{item_id}")

    assert undone.status_code == 200
    assert undone.json()["status"] == "pending"
    assert undone.json()["ledger_transaction_id"] is None
    assert _ledger_status(approved["ledger_transaction_id"]) == "void"


def test_approve_as_transfer_posts_one_ledger_transaction(api_client: TestClient) -> None:
    ids = _seed_accounts()
    debit_id = _stage(gmail_message_id="transfer-debit", account_id=ids["Bank"])
    credit_id = _stage(
        gmail_message_id="transfer-credit",
        account_id=ids["Bank 2"],
        tx_type="credit",
    )

    response = api_client.post(
        "/api/email-inbox/approve-as-transfer",
        json={"debit_id": debit_id, "credit_id": credit_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transfer_pair_id"] == f"ledger:{body['ledger_transaction_id']}"
    assert body["debit_transaction_id"] == body["ledger_transaction_id"]
    assert body["credit_transaction_id"] == body["ledger_transaction_id"]
    assert body["debit_item"]["ledger_transaction_id"] == body["ledger_transaction_id"]
    assert body["credit_item"]["ledger_transaction_id"] == body["ledger_transaction_id"]
