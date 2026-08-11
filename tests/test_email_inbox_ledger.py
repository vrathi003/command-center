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
    assert duplicate.status_code == 200
    body = duplicate.json()
    assert body["status"] == "quarantined"
    assert body["intake_candidate_id"] is not None

    forced = api_client.post(f"/api/email-inbox/{second_item}/approve", json={"force": True})
    assert forced.status_code == 200
    assert forced.json()["status"] == "approved"
    assert forced.json()["ledger_transaction_id"] is not None


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


def _candidate_status(candidate_id: int) -> str:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    row = conn.execute(
        "SELECT status FROM intake_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    return str(row[0])


def _insert_email_candidate(
    *,
    staging_id: int,
    account_id: int,
    amount_paise: int = 12_500,
) -> int:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    cursor = conn.execute(
        """
        INSERT INTO intake_candidates (
            status, source, external_key, tx_date, amount_paise, direction, payee,
            narration, suggested_account_id, suggested_category, confidence,
            quarantine_reason, email_staging_id
        ) VALUES ('pending', 'email', ?, '2026-08-01', ?, 'out', 'Coffee Shop',
                  'UPI Coffee Shop', ?, 'Food', 1.0, 'possible_duplicate', ?)
        """,
        (f"gmail:api-candidate-{staging_id}", amount_paise, account_id, staging_id),
    )
    conn.commit()
    candidate_id = cursor.lastrowid
    conn.close()
    assert candidate_id is not None
    return int(candidate_id)


def _link_staging_to_candidate(item_id: int, candidate_id: int) -> None:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        """
        UPDATE email_transaction_staging
        SET intake_candidate_id = ?, status = 'quarantined'
        WHERE id = ?
        """,
        (candidate_id, item_id),
    )
    conn.commit()
    conn.close()


def test_reject_staging_rejects_linked_candidate(api_client: TestClient) -> None:
    ids = _seed_accounts()
    item_id = _stage(gmail_message_id="reject-linked", account_id=ids["Bank"])
    candidate_id = _insert_email_candidate(staging_id=item_id, account_id=ids["Bank"])
    _link_staging_to_candidate(item_id, candidate_id)

    response = api_client.post(f"/api/email-inbox/{item_id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert _candidate_status(candidate_id) == "rejected"


def test_intake_candidate_approve_syncs_linked_staging(api_client: TestClient) -> None:
    ids = _seed_accounts()
    item_id = _stage(gmail_message_id="intake-approve-sync", account_id=ids["Bank"])
    candidate_id = _insert_email_candidate(staging_id=item_id, account_id=ids["Bank"])
    _link_staging_to_candidate(item_id, candidate_id)

    response = api_client.post(f"/api/intake/candidates/{candidate_id}/approve")

    assert response.status_code == 200
    staging = api_client.get("/api/email-inbox/?status=approved").json()
    approved = next(row for row in staging if row["id"] == item_id)
    assert approved["status"] == "approved"
    assert approved["ledger_transaction_id"] == response.json()["ledger_transaction_id"]


def test_intake_candidate_reject_syncs_linked_staging(api_client: TestClient) -> None:
    ids = _seed_accounts()
    item_id = _stage(gmail_message_id="intake-reject-sync", account_id=ids["Bank"])
    candidate_id = _insert_email_candidate(staging_id=item_id, account_id=ids["Bank"])
    _link_staging_to_candidate(item_id, candidate_id)

    response = api_client.post(f"/api/intake/candidates/{candidate_id}/reject")

    assert response.status_code == 200
    conn = sqlite3.connect(os.environ["DB_PATH"])
    row = conn.execute(
        "SELECT status FROM email_transaction_staging WHERE id = ?", (item_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert str(row[0]) == "rejected"


def test_approve_as_transfer_quarantines_soft_duplicate(api_client: TestClient) -> None:
    ids = _seed_accounts()
    first_item = _stage(gmail_message_id="xfer-first", account_id=ids["Bank"])
    assert api_client.post(f"/api/email-inbox/{first_item}/approve", json={}).status_code == 200
    debit_id = _stage(gmail_message_id="xfer-dupe-debit", account_id=ids["Bank"])
    credit_id = _stage(
        gmail_message_id="xfer-dupe-credit",
        account_id=ids["Bank 2"],
        tx_type="credit",
    )

    response = api_client.post(
        "/api/email-inbox/approve-as-transfer",
        json={"debit_id": debit_id, "credit_id": credit_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ledger_transaction_id"] is None
    assert body["debit_item"]["status"] == "quarantined"
    assert body["credit_item"]["status"] == "quarantined"
    assert body["debit_item"]["intake_candidate_id"] == body["credit_item"]["intake_candidate_id"]


def test_force_approve_from_quarantined_updates_existing_candidate(
    api_client: TestClient,
) -> None:
    ids = _seed_accounts()
    first_item = _stage(gmail_message_id="force-existing-1", account_id=ids["Bank"])
    assert api_client.post(f"/api/email-inbox/{first_item}/approve", json={}).status_code == 200
    second_item = _stage(gmail_message_id="force-existing-2", account_id=ids["Bank"])
    quarantined = api_client.post(f"/api/email-inbox/{second_item}/approve", json={}).json()
    candidate_id = quarantined["intake_candidate_id"]

    forced = api_client.post(f"/api/email-inbox/{second_item}/approve", json={"force": True})

    assert forced.status_code == 200
    assert forced.json()["status"] == "approved"
    assert _candidate_status(candidate_id) == "posted"
    conn = sqlite3.connect(os.environ["DB_PATH"])
    count = conn.execute(
        "SELECT COUNT(*) FROM intake_candidates WHERE source = 'email'"
    ).fetchone()[0]
    conn.close()
    assert count == 2
