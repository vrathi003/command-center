"""Transaction CRUD uses the ledger when ledger_engine is double_entry (no cutover)."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _seed_cash_accounts() -> dict[str, int]:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    accounts = [
        ("Bank", "savings", "asset_cash"),
        ("Bank 2", "savings", "asset_cash"),
    ]
    conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    conn.commit()
    rows = conn.execute("SELECT id, name FROM accounts WHERE name IN ('Bank', 'Bank 2')").fetchall()
    conn.close()
    return {name: account_id for account_id, name in rows}


def _legacy_transaction_count() -> int:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    count = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    conn.close()
    return count


def _cutover_set() -> bool:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        ("project_config.migration.legacy_cutover_at",),
    ).fetchone()
    conn.close()
    return bool(row and str(row[0]).strip())


def test_double_entry_without_cutover_posts_ledger_not_legacy(
    api_client: TestClient,
) -> None:
    ids = _seed_cash_accounts()
    assert _cutover_set() is False

    created = api_client.post(
        "/api/transactions/",
        json={
            "date": "2026-08-11",
            "amount_paise": 12_500,
            "category": "Food",
            "merchant": "Cafe",
            "payment_mode": "UPI",
            "transaction_type": "debit",
            "account_id": ids["Bank"],
            "notes": "lunch",
        },
    )
    assert created.status_code == 201, created.text
    tid = int(created.json()["id"])
    assert _legacy_transaction_count() == 0

    listed = api_client.get("/api/transactions/")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == tid
    assert listed.json()[0]["merchant"] == "Cafe"

    transfer = api_client.post(
        "/api/transactions/transfer",
        json={
            "date": "2026-08-11",
            "amount_paise": 5_000,
            "from_account_id": ids["Bank"],
            "to_account_id": ids["Bank 2"],
        },
    )
    assert transfer.status_code == 201, transfer.text
    assert transfer.json()["transfer_pair_id"].startswith("ledger:")
    assert _legacy_transaction_count() == 0

    updated = api_client.put(
        f"/api/transactions/{tid}",
        json={
            "date": "2026-08-11",
            "amount_paise": 15_000,
            "category": "Food",
            "merchant": "Cafe",
            "payment_mode": "UPI",
            "transaction_type": "debit",
            "account_id": ids["Bank"],
        },
    )
    assert updated.status_code == 200, updated.text
    new_id = int(updated.json()["id"])
    assert new_id != tid

    deleted = api_client.post("/api/transactions/bulk-delete", json={"ids": [new_id]})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": 1}
