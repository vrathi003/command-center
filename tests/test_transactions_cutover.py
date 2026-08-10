"""Manual transaction writers use the ledger after legacy cutover."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _seed_accounts_and_cutover() -> dict[str, int]:
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
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        ("project_config.migration.legacy_cutover_at", "2026-08-10T12:00:00+00:00"),
    )
    conn.commit()
    rows = conn.execute("SELECT id, name FROM accounts").fetchall()
    conn.close()
    return {name: account_id for account_id, name in rows}


def _legacy_transaction_count() -> int:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    count = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    conn.close()
    return count


def _manual_debit(account_id: int, *, amount_paise: int = 50_000) -> dict[str, object]:
    return {
        "date": "2026-08-10",
        "amount_paise": amount_paise,
        "category": "Food",
        "merchant": "Grocer",
        "payment_mode": "UPI",
        "transaction_type": "debit",
        "account_id": account_id,
        "notes": "Weekly shop",
        "tags": "groceries",
    }


def test_cutover_manual_create_posts_ledger_and_lists_legacy_shape(
    api_client: TestClient,
) -> None:
    ids = _seed_accounts_and_cutover()

    response = api_client.post("/api/transactions/", json=_manual_debit(ids["Bank"]))

    assert response.status_code == 201, response.text
    transaction_id = int(response.json()["id"])
    assert _legacy_transaction_count() == 0
    listed = api_client.get("/api/transactions/")
    assert listed.status_code == 200
    assert listed.json()[0] == {
        "id": transaction_id,
        "date": "2026-08-10",
        "amount_paise": 50_000,
        "category": "Food",
        "merchant": "Grocer",
        "payment_mode": "Other",
        "account": "Bank",
        "notes": "Weekly shop",
        "transaction_type": "debit",
        "source": "dashboard",
        "account_id": ids["Bank"],
        "transfer_pair_id": None,
        "tags": "groceries",
    }


def test_cutover_transfer_posts_one_ledger_transaction(api_client: TestClient) -> None:
    ids = _seed_accounts_and_cutover()

    response = api_client.post(
        "/api/transactions/transfer",
        json={
            "date": "2026-08-10",
            "amount_paise": 25_000,
            "from_account_id": ids["Bank"],
            "to_account_id": ids["Bank 2"],
            "notes": "Move funds",
        },
    )

    assert response.status_code == 201, response.text
    transaction_id = int(response.json()["debit_transaction_id"])
    assert response.json() == {
        "transfer_pair_id": f"ledger:{transaction_id}",
        "debit_transaction_id": transaction_id,
        "credit_transaction_id": transaction_id,
    }
    assert _legacy_transaction_count() == 0


def test_cutover_update_voids_and_reposts_then_bulk_delete_voids(
    api_client: TestClient,
) -> None:
    ids = _seed_accounts_and_cutover()
    created = api_client.post("/api/transactions/", json=_manual_debit(ids["Bank"]))
    assert created.status_code == 201, created.text
    old_id = int(created.json()["id"])

    updated = api_client.put(
        f"/api/transactions/{old_id}",
        json=_manual_debit(ids["Bank"], amount_paise=75_000),
    )

    assert updated.status_code == 200, updated.text
    new_id = int(updated.json()["id"])
    assert new_id != old_id
    deleted = api_client.post("/api/transactions/bulk-delete", json={"ids": [new_id]})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"deleted": 1}
    assert api_client.get("/api/transactions/").json() == []
    conn = sqlite3.connect(os.environ["DB_PATH"])
    statuses = conn.execute(
        "SELECT id, status FROM ledger_transactions ORDER BY id"
    ).fetchall()
    conn.close()
    assert statuses == [(old_id, "void"), (new_id, "void")]
