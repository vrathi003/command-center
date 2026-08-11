"""Investment and fixed-income opening seed ledger tests."""

from __future__ import annotations

import os
import sqlite3

from starlette.testclient import TestClient


def _create_bank(api_client: TestClient) -> int:
    bank = api_client.post(
        "/api/accounts/",
        json={"name": "HDFC Savings", "type": "savings", "account_class": "asset_cash"},
    )
    assert bank.status_code == 201, bank.text
    return int(bank.json()["id"])


def _seed_bank_balance(api_client: TestClient, *, bank_id: int, amount_paise: int) -> None:
    accounts = api_client.get("/api/accounts/")
    assert accounts.status_code == 200, accounts.text
    equity = next(
        a for a in accounts.json() if a["name"] == "Opening Balance Equity"
    )
    equity_id = int(equity["id"])

    response = api_client.post(
        "/api/ledger/transactions",
        json={
            "pattern": "custom",
            "date": "2026-07-01",
            "postings": [
                {"account_id": bank_id, "amount_paise": amount_paise},
                {"account_id": equity_id, "amount_paise": -amount_paise},
            ],
            "source": "dashboard",
            "notes": "Seed bank",
        },
    )
    assert response.status_code == 201, response.text


def _balance(api_client: TestClient, account_id: int) -> int:
    response = api_client.get(f"/api/ledger/accounts/{account_id}/balance")
    assert response.status_code == 200, response.text
    return int(response.json()["balance_paise"])


def _equity_id(api_client: TestClient) -> int:
    accounts = api_client.get("/api/accounts/")
    assert accounts.status_code == 200, accounts.text
    equity = next(
        a for a in accounts.json() if a["name"] == "Opening Balance Equity"
    )
    return int(equity["id"])


def _ledger_transaction_count() -> int:
    conn = sqlite3.connect(os.environ["DB_PATH"])
    count = conn.execute("SELECT COUNT(*) FROM ledger_transactions").fetchone()
    conn.close()
    assert count is not None
    return int(count[0])


def _create_investment(api_client: TestClient) -> dict[str, object]:
    response = api_client.post(
        "/api/investments/",
        json={
            "instrument": "Nifty 50 ETF",
            "type": "ETF",
            "units": 10.0,
            "avg_price_paise": 25_000_00,
            "current_price_paise": 26_000_00,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_fixed_income(api_client: TestClient) -> dict[str, object]:
    response = api_client.post(
        "/api/fixed-income/",
        json={
            "institution": "SBI",
            "type": "FD",
            "principal_paise": 500_000_00,
            "rate_percent": 7.0,
            "start_date": "2025-01-01",
            "maturity_date": "2026-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_investment_seed_creates_balanced_postings(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=1_000_000_00)
    equity_id = _equity_id(api_client)

    bank_before = _balance(api_client, bank_id)
    equity_before = _balance(api_client, equity_id)
    ledger_before = _ledger_transaction_count()

    inv = _create_investment(api_client)
    inv_id = int(inv["id"])
    assert inv["account_id"] is not None
    inv_account_id = int(inv["account_id"])
    expected_cost = 250_000_00  # 10 * 25000

    inv_balance = _balance(api_client, inv_account_id)
    assert inv_balance == expected_cost
    assert _balance(api_client, bank_id) == bank_before
    assert _balance(api_client, equity_id) == equity_before - expected_cost
    assert _ledger_transaction_count() == ledger_before + 1

    conn = sqlite3.connect(os.environ["DB_PATH"])
    ext = conn.execute(
        "SELECT external_key FROM ledger_transactions WHERE external_key = ?",
        (f"inv_seed:{inv_id}",),
    ).fetchone()
    conn.close()
    assert ext is not None


def test_investment_second_ensure_is_noop(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=1_000_000_00)

    inv = _create_investment(api_client)
    inv_account_id = int(inv["account_id"])
    equity_id = _equity_id(api_client)

    inv_balance = _balance(api_client, inv_account_id)
    bank_balance = _balance(api_client, bank_id)
    equity_balance = _balance(api_client, equity_id)
    ledger_count = _ledger_transaction_count()

    listed = api_client.get("/api/investments/")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["account_id"] == inv_account_id

    assert _balance(api_client, inv_account_id) == inv_balance
    assert _balance(api_client, bank_id) == bank_balance
    assert _balance(api_client, equity_id) == equity_balance
    assert _ledger_transaction_count() == ledger_count


def test_fixed_income_seed_creates_balanced_postings(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=1_000_000_00)
    equity_id = _equity_id(api_client)

    bank_before = _balance(api_client, bank_id)
    equity_before = _balance(api_client, equity_id)
    ledger_before = _ledger_transaction_count()

    fi = _create_fixed_income(api_client)
    fi_id = int(fi["id"])
    assert fi["account_id"] is not None
    fi_account_id = int(fi["account_id"])
    expected_principal = 500_000_00

    fi_balance = _balance(api_client, fi_account_id)
    assert fi_balance == expected_principal
    assert _balance(api_client, bank_id) == bank_before
    assert _balance(api_client, equity_id) == equity_before - expected_principal
    assert _ledger_transaction_count() == ledger_before + 1

    conn = sqlite3.connect(os.environ["DB_PATH"])
    ext = conn.execute(
        "SELECT external_key FROM ledger_transactions WHERE external_key = ?",
        (f"fi_seed:{fi_id}",),
    ).fetchone()
    conn.close()
    assert ext is not None


def test_fixed_income_second_ensure_is_noop(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=1_000_000_00)

    fi = _create_fixed_income(api_client)
    fi_account_id = int(fi["account_id"])
    equity_id = _equity_id(api_client)

    fi_balance = _balance(api_client, fi_account_id)
    bank_balance = _balance(api_client, bank_id)
    equity_balance = _balance(api_client, equity_id)
    ledger_count = _ledger_transaction_count()

    listed = api_client.get("/api/fixed-income/")
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["account_id"] == fi_account_id

    assert _balance(api_client, fi_account_id) == fi_balance
    assert _balance(api_client, bank_id) == bank_balance
    assert _balance(api_client, equity_id) == equity_balance
    assert _ledger_transaction_count() == ledger_count
