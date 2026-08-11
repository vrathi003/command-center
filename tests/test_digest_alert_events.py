"""Weekly/monthly digests emit AlertService domain events (DE-aware totals)."""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from finance_api.services.background_jobs import job_monthly_discord, job_weekly_discord
from finance_api.settings import ApiSettings
from finance_common.alerts.service import poll_once
from finance_common.db import open_db


def _seed_bank_and_spend(api_client: TestClient) -> None:
    bank = api_client.post(
        "/api/accounts/",
        json={"name": "Bank", "type": "savings", "account_class": "asset_cash"},
    )
    assert bank.status_code == 201, bank.text
    bank_id = int(bank.json()["id"])
    posted = api_client.post(
        "/api/transactions/",
        json={
            "date": date.today().isoformat(),
            "amount_paise": 25_000,
            "category": "Food",
            "merchant": "Cafe",
            "payment_mode": "UPI",
            "transaction_type": "debit",
            "account_id": bank_id,
        },
    )
    assert posted.status_code == 201, posted.text


@pytest.mark.asyncio
async def test_weekly_digest_emits_event_and_in_app_alert(api_client: TestClient) -> None:
    _seed_bank_and_spend(api_client)
    settings = ApiSettings()
    db_path = Path(os.environ["DB_PATH"])

    with patch(
        "finance_api.services.background_jobs.send_discord_dm",
        new_callable=AsyncMock,
    ):
        await job_weekly_discord(db_path, settings)

    conn = sqlite3.connect(os.environ["DB_PATH"])
    events = conn.execute(
        "SELECT event_type FROM domain_events WHERE event_type = 'digest.weekly'"
    ).fetchall()
    conn.close()
    assert len(events) == 1

    async with open_db(db_path) as aconn:
        n = await poll_once(aconn)
    assert n >= 1

    conn = sqlite3.connect(os.environ["DB_PATH"])
    alerts = conn.execute(
        "SELECT kind, title FROM alert_notifications WHERE kind = 'digest'"
    ).fetchall()
    conn.close()
    assert len(alerts) == 1
    assert alerts[0][1] == "Weekly finance digest"


@pytest.mark.asyncio
async def test_monthly_digest_emits_event(api_client: TestClient) -> None:
    _seed_bank_and_spend(api_client)
    settings = ApiSettings()
    db_path = Path(os.environ["DB_PATH"])
    with patch(
        "finance_api.services.background_jobs.send_discord_dm",
        new_callable=AsyncMock,
    ):
        await job_monthly_discord(db_path, settings)

    conn = sqlite3.connect(os.environ["DB_PATH"])
    events = conn.execute(
        "SELECT event_type FROM domain_events WHERE event_type = 'digest.monthly'"
    ).fetchall()
    conn.close()
    assert len(events) == 1
