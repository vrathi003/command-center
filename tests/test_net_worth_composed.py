"""Net worth composed lens (ledger + MV overlay) tests."""

from __future__ import annotations

import os
import sqlite3

import aiosqlite
import pytest
from starlette.testclient import TestClient

from finance_api.services.net_worth_service import (
    compute_net_worth_composed,
    compute_totals_from_holdings,
)


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
    equity = next(a for a in accounts.json() if a["name"] == "Opening Balance Equity")
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


@pytest.mark.asyncio
async def test_composed_net_worth_seed_and_buy(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=1_000_000_00)

    inv = _create_investment(api_client)
    inv_id = int(inv["id"])
    buy_amount = 50_000_00

    buy = api_client.post(
        f"/api/investments/{inv_id}/record-buy",
        json={
            "date": "2026-08-01",
            "amount_paise": buy_amount,
            "units": 5.0,
            "bank_account_id": bank_id,
        },
    )
    assert buy.status_code == 201, buy.text

    # Ledger: bank 950k + inv cost 300k; MV overlay replaces cost with 390k.
    expected_assets = 1_340_000_00
    expected_liabilities = 0
    expected_net = expected_assets - expected_liabilities

    async with aiosqlite.connect(os.environ["DB_PATH"]) as conn:
        assets, liabilities, net = await compute_net_worth_composed(conn)
        assert assets == expected_assets
        assert liabilities == expected_liabilities
        assert net == expected_net

        disp_assets, disp_liabilities, disp_net = await compute_totals_from_holdings(conn)
        assert disp_assets == expected_assets
        assert disp_liabilities == expected_liabilities
        assert disp_net == expected_net


def test_legacy_holdings_path_when_not_double_entry(api_client: TestClient) -> None:
    api_client.put(
        "/api/settings/",
        json={"project_config": {"ledger_engine": "legacy"}},
    )

    api_client.post(
        "/api/investments/",
        json={
            "instrument": "Legacy MF",
            "type": "MF",
            "units": 2.0,
            "avg_price_paise": 10_000_00,
            "current_price_paise": 12_000_00,
        },
    )

    snap = api_client.post("/api/net-worth/snapshot", json={"computed_from_holdings": True})
    assert snap.status_code == 201, snap.text
    # Holdings-only: 2 * 12000 = 24000
    assert snap.json()["total_assets_paise"] == 24_000_00
    assert snap.json()["total_liabilities_paise"] == 0


def test_unbound_debt_added_to_liabilities(api_client: TestClient) -> None:
    bank_id = _create_bank(api_client)
    _seed_bank_balance(api_client, bank_id=bank_id, amount_paise=100_000_00)

    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.execute(
        """
        INSERT INTO debts (
            name, type, original_amount_paise, current_balance_paise,
            rate_percent, status
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("Informal loan", "personal", 50_000_00, 50_000_00, 0.0, "active"),
    )
    conn.commit()
    debt_row = conn.execute("SELECT account_id FROM debts LIMIT 1").fetchone()
    conn.close()
    assert debt_row is not None
    assert debt_row[0] is None

    snap = api_client.post("/api/net-worth/snapshot", json={"computed_from_holdings": True})
    assert snap.status_code == 201, snap.text
    body = snap.json()
    assert body["total_liabilities_paise"] == 50_000_00
    assert body["total_assets_paise"] == 100_000_00
    assert body["net_worth_paise"] == 50_000_00
