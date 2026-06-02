"""Transaction GET (detail) and PUT (dashboard edit)."""

from __future__ import annotations

import os
import sqlite3
import uuid

from starlette.testclient import TestClient


def test_get_and_put_debit_transaction(api_client: TestClient) -> None:
    r1 = api_client.post(
        "/api/accounts/",
        json={"name": "Test Savings", "type": "savings", "currency": "INR"},
    )
    assert r1.status_code == 201, r1.text
    aid = r1.json()["id"]

    r2 = api_client.post(
        "/api/transactions/",
        json={
            "date": "2025-06-15",
            "amount_paise": 12_345,
            "category": "Other",
            "merchant": "Coffee",
            "payment_mode": "UPI",
            "transaction_type": "debit",
            "account_id": aid,
            "source": "dashboard",
        },
    )
    assert r2.status_code == 201, r2.text
    tid = r2.json()["id"]

    r3 = api_client.get(f"/api/transactions/{tid}")
    assert r3.status_code == 200, r3.text
    body = r3.json()
    assert body["id"] == tid
    assert body["merchant"] == "Coffee"
    assert body["transfer_sibling"] is None

    r4 = api_client.put(
        f"/api/transactions/{tid}",
        json={
            "date": "2025-06-16",
            "amount_paise": 99_00,
            "category": "Groceries",
            "merchant": "Mart",
            "payment_mode": "Cash",
            "transaction_type": "debit",
            "account_id": aid,
            "notes": "n",
            "tags": "t1",
        },
    )
    assert r4.status_code == 200, r4.text

    r5 = api_client.get(f"/api/transactions/{tid}")
    assert r5.status_code == 200
    u = r5.json()
    assert u["date"] == "2025-06-16"
    assert u["amount_paise"] == 99_00
    assert u["category"] == "Groceries"
    assert u["merchant"] == "Mart"
    assert u["payment_mode"] == "Cash"
    assert u["notes"] == "n"
    assert u["tags"] == "t1"


def test_put_transfer_pair(api_client: TestClient) -> None:
    r1 = api_client.post("/api/accounts/", json={"name": "A1", "type": "savings", "currency": "INR"})
    r2 = api_client.post("/api/accounts/", json={"name": "A2", "type": "savings", "currency": "INR"})
    assert r1.status_code == 201 and r2.status_code == 201
    a1, a2 = r1.json()["id"], r2.json()["id"]

    r3 = api_client.post(
        "/api/transactions/transfer",
        json={
            "date": "2025-07-01",
            "amount_paise": 50_000,
            "from_account_id": a1,
            "to_account_id": a2,
        },
    )
    assert r3.status_code == 201, r3.text
    out_id = r3.json()["debit_transaction_id"]

    r4 = api_client.put(
        f"/api/transactions/{out_id}",
        json={
            "date": "2025-07-02",
            "amount_paise": 75_000,
            "from_account_id": a2,
            "to_account_id": a1,
            "notes": "swap",
        },
    )
    assert r4.status_code == 200, r4.text

    lst = api_client.get("/api/transactions/?limit=20").json()
    pair = [x for x in lst if x["id"] in (r3.json()["debit_transaction_id"], r3.json()["credit_transaction_id"])]
    assert len(pair) == 2
    assert all(x["date"] == "2025-07-02" for x in pair)
    assert all(x["amount_paise"] == 75_000 for x in pair)
    assert {x["account"] for x in pair} == {"A1", "A2"}


def test_put_paired_transfer_noncanonical_merchant(api_client: TestClient) -> None:
    """Pair updates must work when merchants are not Transfer out/in (e.g. import)."""
    r1 = api_client.post("/api/accounts/", json={"name": "X1", "type": "savings", "currency": "INR"})
    r2 = api_client.post("/api/accounts/", json={"name": "X2", "type": "savings", "currency": "INR"})
    assert r1.status_code == 201 and r2.status_code == 201
    a1, a2 = r1.json()["id"], r2.json()["id"]
    pair_id = str(uuid.uuid4())
    db_path = os.environ["DB_PATH"]
    conn = sqlite3.connect(db_path)
    for acc_id, acc_name, merch in ((a1, "X1", "Leg A"), (a2, "X2", "Leg B")):
        conn.execute(
            """
            INSERT INTO transactions (
                date, amount_paise, category, merchant, payment_mode, account, notes,
                transaction_type, source, is_deleted, account_id, transfer_pair_id, tags,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "2025-02-01",
                5555,
                "Transfer",
                merch,
                "Bank Transfer",
                acc_name,
                None,
                "transfer",
                "import",
                0,
                acc_id,
                pair_id,
                None,
            ),
        )
    conn.commit()
    tid = conn.execute(
        "SELECT id FROM transactions WHERE transfer_pair_id = ? ORDER BY id LIMIT 1",
        (pair_id,),
    ).fetchone()[0]
    conn.close()

    r = api_client.put(
        f"/api/transactions/{tid}",
        json={
            "date": "2025-02-02",
            "amount_paise": 7777,
            "from_account_id": a2,
            "to_account_id": a1,
            "notes": "n",
        },
    )
    assert r.status_code == 200, r.text

    lst = api_client.get("/api/transactions/?limit=50").json()
    legs = [x for x in lst if x.get("transfer_pair_id") == pair_id]
    assert len(legs) == 2
    assert {m["merchant"] for m in legs} == {"Transfer out", "Transfer in"}
    assert all(x["amount_paise"] == 7777 for x in legs)


def test_put_converts_imported_debit_to_transfer_pair(api_client: TestClient) -> None:
    """Dashboard edit: debit/credit row → transfer creates the matching leg."""
    r1 = api_client.post("/api/accounts/", json={"name": "HDFC Main", "type": "savings", "currency": "INR"})
    r2 = api_client.post("/api/accounts/", json={"name": "HDFC Savings", "type": "savings", "currency": "INR"})
    assert r1.status_code == 201 and r2.status_code == 201
    a1, a2 = r1.json()["id"], r2.json()["id"]

    db_path = os.environ["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO transactions (
            date, amount_paise, category, merchant, payment_mode, account, notes,
            transaction_type, source, is_deleted, account_id, transfer_pair_id, tags,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            "2025-06-15",
            10_000,
            "Other",
            "SELF TRF",
            "NEFT/IMPS",
            "HDFC Main",
            None,
            "debit",
            "import",
            0,
            a1,
            None,
            None,
        ),
    )
    conn.commit()
    tid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.close()

    r = api_client.put(
        f"/api/transactions/{tid}",
        json={
            "date": "2025-06-15",
            "amount_paise": 10_000,
            "from_account_id": a1,
            "to_account_id": a2,
            "notes": "internal move",
        },
    )
    assert r.status_code == 200, r.text

    out = api_client.get(f"/api/transactions/{tid}").json()
    assert out["transaction_type"] == "transfer"
    assert out["merchant"] == "Transfer out"
    assert out["transfer_pair_id"] is not None
    assert out["account_id"] == a1

    sibling = out["transfer_sibling"]
    assert sibling is not None
    assert sibling["merchant"] == "Transfer in"
    assert sibling["account_id"] == a2
    assert sibling["transfer_pair_id"] == out["transfer_pair_id"]
    assert sibling["amount_paise"] == 10_000


def test_put_orphan_transfer_single_leg(api_client: TestClient) -> None:
    """Single-row transfer (no pair id) updates like a normal line."""
    r1 = api_client.post("/api/accounts/", json={"name": "Solo", "type": "savings", "currency": "INR"})
    assert r1.status_code == 201
    aid = r1.json()["id"]
    db_path = os.environ["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO transactions (
            date, amount_paise, category, merchant, payment_mode, account, notes,
            transaction_type, source, is_deleted, account_id, transfer_pair_id, tags,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            "2025-03-01",
            3333,
            "Transfer",
            "NEFT self",
            "NEFT/IMPS",
            "Solo",
            None,
            "transfer",
            "import",
            0,
            aid,
            None,
            None,
        ),
    )
    conn.commit()
    tid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.close()

    r = api_client.put(
        f"/api/transactions/{tid}",
        json={
            "date": "2025-03-02",
            "amount_paise": 4444,
            "category": "Transfer",
            "merchant": "Updated narration",
            "payment_mode": "Bank Transfer",
            "account_id": aid,
            "notes": "x",
            "tags": "y",
        },
    )
    assert r.status_code == 200, r.text
    row = api_client.get(f"/api/transactions/{tid}").json()
    assert row["date"] == "2025-03-02"
    assert row["amount_paise"] == 4444
    assert row["merchant"] == "Updated narration"
    assert row["transaction_type"] == "transfer"
    assert row["transfer_pair_id"] is None
