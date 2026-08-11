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


def _create_empty_investment(api_client: TestClient) -> dict[str, object]:
    response = api_client.post(
        "/api/investments/",
        json={
            "instrument": "Parag Parikh Flexi Cap",
            "type": "MF",
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


def test_record_buy_reduces_bank_increases_inv_updates_units_avg(
    api_client: TestClient,
) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=500_000_00)

    inv = _create_empty_investment(api_client)
    inv_id = int(inv["id"])
    inv_account_id = int(inv["account_id"])

    bank_before = _balance(api_client, bank_id)
    inv_before = _balance(api_client, inv_account_id)
    buy_amount = 50_000_00
    buy_units = 5.0

    response = api_client.post(
        f"/api/investments/{inv_id}/record-buy",
        json={
            "date": "2026-08-01",
            "amount_paise": buy_amount,
            "units": buy_units,
            "bank_account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert int(body["ledger_transaction_id"]) > 0
    updated = body["investment"]
    assert updated["units"] == buy_units
    assert updated["avg_price_paise"] == 10_000_00  # 50000 / 5
    assert updated["cost_basis_paise"] == buy_amount

    assert _balance(api_client, bank_id) == bank_before - buy_amount
    assert _balance(api_client, inv_account_id) == inv_before + buy_amount


def test_record_sell_reverses_buy(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=500_000_00)

    inv = _create_empty_investment(api_client)
    inv_id = int(inv["id"])
    inv_account_id = int(inv["account_id"])

    buy_response = api_client.post(
        f"/api/investments/{inv_id}/record-buy",
        json={
            "date": "2026-08-01",
            "amount_paise": 50_000_00,
            "units": 5.0,
            "bank_account_id": bank_id,
        },
    )
    assert buy_response.status_code == 201, buy_response.text

    bank_before = _balance(api_client, bank_id)
    inv_before = _balance(api_client, inv_account_id)
    sell_amount = 20_000_00
    sell_units = 2.0

    response = api_client.post(
        f"/api/investments/{inv_id}/record-sell",
        json={
            "date": "2026-08-15",
            "amount_paise": sell_amount,
            "units": sell_units,
            "bank_account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert int(body["ledger_transaction_id"]) > 0
    updated = body["investment"]
    assert updated["units"] == 3.0
    assert updated["avg_price_paise"] == 10_000_00
    assert updated["cost_basis_paise"] == 30_000_00

    assert _balance(api_client, bank_id) == bank_before + sell_amount
    assert _balance(api_client, inv_account_id) == inv_before - sell_amount


def test_record_buy_requires_double_entry(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    inv = _create_empty_investment(api_client)
    inv_id = int(inv["id"])

    api_client.put(
        "/api/settings/",
        json={"project_config": {"ledger_engine": "legacy"}},
    )

    response = api_client.post(
        f"/api/investments/{inv_id}/record-buy",
        json={
            "date": "2026-08-01",
            "amount_paise": 10_000_00,
            "units": 1.0,
            "bank_account_id": bank_id,
        },
    )
    assert response.status_code == 422
    assert "double_entry" in response.json()["detail"]


def _create_empty_fixed_income(api_client: TestClient) -> dict[str, object]:
    response = api_client.post(
        "/api/fixed-income/",
        json={
            "institution": "Post Office RD",
            "type": "RD",
            "principal_paise": 0,
            "rate_percent": 6.5,
            "start_date": "2026-01-01",
            "maturity_date": "2027-01-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_record_deposit_reduces_bank_increases_fi_principal(
    api_client: TestClient,
) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=500_000_00)

    fi = _create_empty_fixed_income(api_client)
    fi_id = int(fi["id"])
    fi_account_id = int(fi["account_id"])

    bank_before = _balance(api_client, bank_id)
    fi_before = _balance(api_client, fi_account_id)
    deposit_amount = 100_000_00

    response = api_client.post(
        f"/api/fixed-income/{fi_id}/record-deposit",
        json={
            "date": "2026-08-01",
            "amount_paise": deposit_amount,
            "bank_account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert int(body["ledger_transaction_id"]) > 0
    updated = body["fixed_income"]
    assert updated["principal_paise"] == deposit_amount

    assert _balance(api_client, bank_id) == bank_before - deposit_amount
    assert _balance(api_client, fi_account_id) == fi_before + deposit_amount


def test_record_maturity_reverses_deposit(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=500_000_00)

    fi = _create_empty_fixed_income(api_client)
    fi_id = int(fi["id"])
    fi_account_id = int(fi["account_id"])

    deposit_amount = 200_000_00
    deposit_response = api_client.post(
        f"/api/fixed-income/{fi_id}/record-deposit",
        json={
            "date": "2026-08-01",
            "amount_paise": deposit_amount,
            "bank_account_id": bank_id,
        },
    )
    assert deposit_response.status_code == 201, deposit_response.text

    bank_before = _balance(api_client, bank_id)
    fi_before = _balance(api_client, fi_account_id)

    response = api_client.post(
        f"/api/fixed-income/{fi_id}/record-maturity",
        json={
            "date": "2026-08-15",
            "bank_account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert int(body["ledger_transaction_id"]) > 0
    updated = body["fixed_income"]
    assert updated["principal_paise"] == 0

    assert _balance(api_client, bank_id) == bank_before + deposit_amount
    assert _balance(api_client, fi_account_id) == fi_before - deposit_amount


def test_record_maturity_partial_reduces_principal(
    api_client: TestClient,
) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=1_000_000_00)

    fi = _create_fixed_income(api_client)
    fi_id = int(fi["id"])
    fi_account_id = int(fi["account_id"])
    original_principal = int(fi["principal_paise"])
    withdraw_amount = 200_000_00

    response = api_client.post(
        f"/api/fixed-income/{fi_id}/record-maturity",
        json={
            "date": "2026-08-15",
            "amount_paise": withdraw_amount,
            "bank_account_id": bank_id,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    updated = body["fixed_income"]
    assert updated["principal_paise"] == original_principal - withdraw_amount

    fi_balance = _balance(api_client, fi_account_id)
    assert fi_balance == original_principal - withdraw_amount


def test_record_deposit_requires_double_entry(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    fi = _create_empty_fixed_income(api_client)
    fi_id = int(fi["id"])

    api_client.put(
        "/api/settings/",
        json={"project_config": {"ledger_engine": "legacy"}},
    )

    response = api_client.post(
        f"/api/fixed-income/{fi_id}/record-deposit",
        json={
            "date": "2026-08-01",
            "amount_paise": 10_000_00,
            "bank_account_id": bank_id,
        },
    )
    assert response.status_code == 422
    assert "double_entry" in response.json()["detail"]
