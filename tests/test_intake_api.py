"""HTTP tests for intake quarantine review."""

from __future__ import annotations

import json
import os
import sqlite3

from starlette.testclient import TestClient


def _seed_accounts_and_candidate(*, direction: str = "out") -> tuple[dict[str, int], int]:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    accounts = [
        ("Bank", "savings", "asset_cash"),
        ("Bank 2", "savings", "asset_cash"),
        ("Expense", "expense", "expense"),
    ]
    conn.executemany(
        "INSERT INTO accounts (name, type, account_class) VALUES (?, ?, ?)",
        accounts,
    )
    ids = {
        name: account_id
        for account_id, name in conn.execute(
            "SELECT id, name FROM accounts WHERE name IN (?, ?, ?)",
            tuple(account[0] for account in accounts),
        )
    }
    cursor = conn.execute(
        """
        INSERT INTO intake_candidates (
            status, source, external_key, tx_date, amount_paise, direction, payee,
            narration, suggested_account_id, suggested_counter_account_id,
            suggested_category, confidence, quarantine_reason
        ) VALUES ('pending', 'import', 'import:row:1', '2026-08-05', 12_345, ?, 'Coffee Shop',
                  'UPI Coffee Shop', ?, ?, 'Dining', 0.5, 'low_confidence')
        """,
        (direction, ids["Bank"], ids["Expense"]),
    )
    conn.commit()
    candidate_id = int(cursor.lastrowid)
    conn.close()
    return ids, candidate_id


def test_list_pending_intake_candidates(api_client: TestClient) -> None:
    ids, candidate_id = _seed_accounts_and_candidate()

    response = api_client.get("/api/intake/candidates")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": candidate_id,
            "status": "pending",
            "source": "import",
            "tx_date": "2026-08-05",
            "amount_paise": 12_345,
            "direction": "out",
            "payee": "Coffee Shop",
            "narration": "UPI Coffee Shop",
            "suggested_account_id": ids["Bank"],
            "suggested_counter_account_id": ids["Expense"],
            "suggested_category": "Dining",
            "confidence": 0.5,
            "quarantine_reason": "low_confidence",
            "ledger_transaction_id": None,
            "external_key": "import:row:1",
        }
    ]


def test_approve_intake_candidate_posts_ledger_transaction(api_client: TestClient) -> None:
    ids, candidate_id = _seed_accounts_and_candidate()

    response = api_client.post(f"/api/intake/candidates/{candidate_id}/approve")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "candidate_id": candidate_id,
        "ledger_transaction_id": response.json()["ledger_transaction_id"],
        "status": "posted",
    }
    ledger_transaction_id = response.json()["ledger_transaction_id"]
    transaction = api_client.get(f"/api/ledger/transactions/{ledger_transaction_id}")
    assert transaction.status_code == 200
    assert transaction.json()["postings"] == [
        {"id": 1, "account_id": ids["Expense"], "amount_paise": 12_345, "category": "Dining"},
        {"id": 2, "account_id": ids["Bank"], "amount_paise": -12_345, "category": None},
    ]
    conn = sqlite3.connect(os.environ["DB_PATH"])
    candidate = conn.execute(
        "SELECT status, quarantine_reason FROM intake_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    event = conn.execute(
        "SELECT event_type, payload_json FROM domain_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert candidate == ("posted", None)
    assert event is not None
    assert event[0] == "intake.candidate_approved"
    assert json.loads(event[1]) == {
        "candidate_id": candidate_id,
        "ledger_transaction_id": response.json()["ledger_transaction_id"],
    }


def test_approve_as_transfer_posts_balanced_transfer(api_client: TestClient) -> None:
    ids, candidate_id = _seed_accounts_and_candidate()

    response = api_client.post(
        f"/api/intake/candidates/{candidate_id}/approve",
        json={"as_transfer": True, "to_account_id": ids["Bank 2"]},
    )

    assert response.status_code == 200, response.text
    ledger_transaction_id = response.json()["ledger_transaction_id"]
    transaction = api_client.get(f"/api/ledger/transactions/{ledger_transaction_id}")
    assert transaction.json()["postings"] == [
        {"id": 1, "account_id": ids["Bank 2"], "amount_paise": 12_345, "category": None},
        {"id": 2, "account_id": ids["Bank"], "amount_paise": -12_345, "category": None},
    ]


def test_approve_opening_balance_posts_balanced_asset_entry(api_client: TestClient) -> None:
    ids, candidate_id = _seed_accounts_and_candidate()
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        """
        UPDATE intake_candidates
        SET amount_paise = 0, quarantine_reason = 'needs_opening_balance'
        WHERE id = ?
        """,
        (candidate_id,),
    )
    opening_balance_equity_id = conn.execute(
        "SELECT id FROM accounts WHERE name = 'Opening Balance Equity'"
    ).fetchone()
    conn.commit()
    conn.close()
    assert opening_balance_equity_id is not None

    missing_amount = api_client.post(
        f"/api/intake/candidates/{candidate_id}/approve",
        json={"account_id": ids["Bank"]},
    )
    assert missing_amount.status_code == 422

    response = api_client.post(
        f"/api/intake/candidates/{candidate_id}/approve",
        json={"account_id": ids["Bank"], "amount_paise": 50_000},
    )

    assert response.status_code == 200, response.text
    ledger_transaction_id = response.json()["ledger_transaction_id"]
    transaction = api_client.get(f"/api/ledger/transactions/{ledger_transaction_id}")
    assert transaction.json()["postings"] == [
        {"id": 1, "account_id": ids["Bank"], "amount_paise": 50_000, "category": None},
        {
            "id": 2,
            "account_id": opening_balance_equity_id[0],
            "amount_paise": -50_000,
            "category": None,
        },
    ]


def test_reject_intake_candidate_emits_event(api_client: TestClient) -> None:
    _, candidate_id = _seed_accounts_and_candidate()

    response = api_client.post(f"/api/intake/candidates/{candidate_id}/reject")

    assert response.status_code == 200
    assert response.json() == {"candidate_id": candidate_id, "status": "rejected"}
    conn = sqlite3.connect(os.environ["DB_PATH"])
    event = conn.execute(
        "SELECT event_type, payload_json FROM domain_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert event is not None
    assert event[0] == "intake.candidate_rejected"
    assert json.loads(event[1]) == {"candidate_id": candidate_id}


def test_approve_non_pending_candidate_returns_conflict(api_client: TestClient) -> None:
    _, candidate_id = _seed_accounts_and_candidate()

    first = api_client.post(f"/api/intake/candidates/{candidate_id}/approve")
    second = api_client.post(f"/api/intake/candidates/{candidate_id}/approve")

    assert first.status_code == 200, first.text
    assert second.status_code == 409
