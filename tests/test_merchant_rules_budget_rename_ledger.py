"""Merchant-rule retroapply and budget rename update ledger books under double_entry."""

from __future__ import annotations

import os
import sqlite3
from urllib.parse import quote

from starlette.testclient import TestClient


def _seed_bank() -> int:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        ("Bank", "savings", "asset_cash"),
    )
    conn.commit()
    bank_id = int(conn.execute("SELECT id FROM accounts WHERE name = 'Bank'").fetchone()[0])
    conn.close()
    return bank_id


def _post_debit(
    api_client: TestClient,
    bank_id: int,
    *,
    merchant: str,
    category: str = "Other",
) -> int:
    response = api_client.post(
        "/api/transactions/",
        json={
            "date": "2026-08-11",
            "amount_paise": 10_000,
            "category": category,
            "merchant": merchant,
            "payment_mode": "UPI",
            "transaction_type": "debit",
            "account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_create_rule_retroactively_applies_to_ledger_payee(
    api_client: TestClient,
) -> None:
    bank_id = _seed_bank()
    _post_debit(api_client, bank_id, merchant="Widgetsmith")
    _post_debit(api_client, bank_id, merchant="Widgetsmith")
    _post_debit(api_client, bank_id, merchant="OtherPlace")

    created = api_client.post(
        "/api/merchant-rules/",
        json={
            "match_type": "exact",
            "match_value": "widgetsmith",
            "canonical_merchant": "Widgetsmith Co",
            "merchant_type": None,
            "category": "Online Shopping",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["retroactively_applied"] == 2

    listed = api_client.get("/api/transactions/?limit=50").json()
    widget = [t for t in listed if t.get("merchant") == "Widgetsmith Co"]
    assert len(widget) == 2
    assert all(t["category"] == "Online Shopping" for t in widget)

    conn = sqlite3.connect(os.environ["DB_PATH"])
    legacy = int(conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
    posting_cats = [
        row[0]
        for row in conn.execute(
            """
            SELECT lp.category
            FROM ledger_postings lp
            JOIN accounts a ON a.id = lp.account_id
            WHERE a.account_class = 'expense' AND lp.category = 'Online Shopping'
            """
        ).fetchall()
    ]
    conn.close()
    assert legacy == 0
    assert len(posting_cats) == 2


def test_rename_budget_category_updates_ledger_postings(api_client: TestClient) -> None:
    bank_id = _seed_bank()
    old = "Rename Ledger Cat"
    new = "Renamed Ledger Cat"
    _post_debit(api_client, bank_id, merchant="Cafe", category=old)

    put = api_client.put(
        f"/api/budget/category/{quote(old, safe='')}",
        json={"monthly_amount_paise": 50_000},
    )
    assert put.status_code == 200, put.text

    renamed = api_client.post(
        "/api/budget/rename-category",
        json={"old_category": old, "new_category": new},
    )
    assert renamed.status_code == 204, renamed.text

    listed = api_client.get("/api/transactions/?limit=10").json()
    assert listed[0]["category"] == new

    conn = sqlite3.connect(os.environ["DB_PATH"])
    n_old = int(
        conn.execute(
            "SELECT COUNT(*) FROM ledger_postings WHERE category = ?", (old,)
        ).fetchone()[0]
    )
    n_new = int(
        conn.execute(
            "SELECT COUNT(*) FROM ledger_postings WHERE category = ?", (new,)
        ).fetchone()[0]
    )
    conn.close()
    assert n_old == 0
    assert n_new >= 1
