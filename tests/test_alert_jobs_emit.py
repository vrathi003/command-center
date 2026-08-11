"""Background alert jobs emit domain events instead of Discord DMs."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from finance_api.services.background_jobs import (
    job_budget_and_alerts,
    job_cc_due_date_alerts,
    job_emi_reminders,
)
from finance_api.settings import ApiSettings
from finance_common.db import ensure_database, open_db
from finance_common.fy import date_to_fy
from finance_common.repositories import budgets as budget_repo
from finance_common.repositories import credit_cards as cc_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories import settings_repo
from finance_common.repositories import transactions as tx_repo

_FIXED_TODAY = date(2026, 8, 11)


async def _list_all_events(db_path: Path) -> list[tuple[str, dict[str, object]]]:
    async with open_db(db_path) as conn:
        cur = await conn.execute(
            "SELECT event_type, payload_json FROM domain_events ORDER BY id",
        )
        rows = await cur.fetchall()
    return [(str(r[0]), json.loads(str(r[1]))) for r in rows]


def _api_no_discord(db_path: Path) -> ApiSettings:
    return ApiSettings(
        db_path=db_path,
        discord_bot_token=None,
        discord_user_id=None,
    )


@pytest.fixture
async def alert_db(tmp_path: Path) -> Path:
    db = tmp_path / "alert_jobs.db"
    await ensure_database(db)
    async with open_db(db) as conn:
        fy = date_to_fy(_FIXED_TODAY)
        await settings_repo.set_value(conn, "current_fy", str(fy))
    return db


@pytest.mark.asyncio
@patch("finance_api.services.background_jobs.send_discord_dm", new_callable=AsyncMock)
@patch("finance_api.services.background_jobs.date")
async def test_job_budget_emits_threshold_events_no_discord(
    mock_date: object,
    mock_dm: AsyncMock,
    alert_db: Path,
) -> None:
    mock_date.today.return_value = _FIXED_TODAY  # type: ignore[attr-defined]
    mock_date.side_effect = lambda *a, **k: date(*a, **k)  # type: ignore[attr-defined]

    async with open_db(alert_db) as conn:
        fy = await settings_repo.get_current_fy(conn)
        month_start = _FIXED_TODAY.replace(day=1)
        await budget_repo.set_monthly_budget(
            conn,
            category="Food",
            fy_year=str(fy),
            monthly_amount_paise=100_000,
            effective_from=month_start,
        )
        await budget_repo.set_monthly_budget(
            conn,
            category="Transport",
            fy_year=str(fy),
            monthly_amount_paise=50_000,
            effective_from=month_start,
        )
        await tx_repo.insert_transaction(
            conn,
            tx_date=_FIXED_TODAY,
            amount_paise=80_000,
            category="Food",
            merchant="Groceries",
            payment_mode="UPI",
            account=None,
            notes=None,
            source="test",
        )
        await tx_repo.insert_transaction(
            conn,
            tx_date=_FIXED_TODAY,
            amount_paise=60_000,
            category="Transport",
            merchant="Fuel",
            payment_mode="UPI",
            account=None,
            notes=None,
            source="test",
        )

    await job_budget_and_alerts(alert_db, _api_no_discord(alert_db))

    mock_dm.assert_not_called()
    events = await _list_all_events(alert_db)
    assert len(events) == 2
    by_cat = {payload["category"]: (etype, payload) for etype, payload in events}
    assert set(by_cat) == {"Food", "Transport"}

    food_type, food = by_cat["Food"]
    assert food_type == "budget.threshold"
    assert food == {
        "ym": "2026-08",
        "category": "Food",
        "status": "warn",
        "spent_paise": 80_000,
        "budget_paise": 100_000,
        "pct": 80.0,
    }

    transport_type, transport = by_cat["Transport"]
    assert transport_type == "budget.threshold"
    assert transport["status"] == "over"
    assert transport["spent_paise"] == 60_000
    assert transport["budget_paise"] == 50_000


@pytest.mark.asyncio
@patch("finance_api.services.background_jobs.send_discord_dm", new_callable=AsyncMock)
@patch("finance_api.services.background_jobs.date")
async def test_job_emi_reminders_emits_events_no_discord(
    mock_date: object,
    mock_dm: AsyncMock,
    alert_db: Path,
) -> None:
    mock_date.today.return_value = _FIXED_TODAY  # type: ignore[attr-defined]
    mock_date.side_effect = lambda *a, **k: date(*a, **k)  # type: ignore[attr-defined]
    mock_date.fromisoformat = date.fromisoformat  # type: ignore[attr-defined]

    due_in_two = (_FIXED_TODAY + timedelta(days=2)).isoformat()
    async with open_db(alert_db) as conn:
        debt_id = await debt_repo.insert_debt(
            conn,
            name="Home loan",
            lender="HDFC",
            type_="Home Loan",
            original_amount_paise=10_000_000,
            current_balance_paise=9_000_000,
            emi_paise=50_000,
            rate_percent=8.5,
            start_date="2025-01-01",
            next_emi_date=due_in_two,
            status="active",
        )

    await job_emi_reminders(alert_db, _api_no_discord(alert_db))

    mock_dm.assert_not_called()
    events = await _list_all_events(alert_db)
    assert len(events) == 1
    etype, payload = events[0]
    assert etype == "debt.emi_due"
    assert payload == {
        "debt_id": debt_id,
        "name": "Home loan",
        "due_date": due_in_two,
        "days_until": 2,
    }


@pytest.mark.asyncio
@patch("finance_api.services.background_jobs.send_discord_dm", new_callable=AsyncMock)
@patch("finance_api.services.background_jobs.date")
async def test_job_cc_due_emits_without_discord_configured(
    mock_date: object,
    mock_dm: AsyncMock,
    alert_db: Path,
) -> None:
    mock_date.today.return_value = _FIXED_TODAY  # type: ignore[attr-defined]
    mock_date.side_effect = lambda *a, **k: date(*a, **k)  # type: ignore[attr-defined]

    async with open_db(alert_db) as conn:
        card_id = await cc_repo.insert_credit_card(
            conn,
            name="HDFC Regalia",
            issuer="HDFC",
            last_four="1234",
            credit_limit_paise=500_000,
            current_balance_paise=None,
            notes=None,
            due_day=_FIXED_TODAY.day,
        )

    await job_cc_due_date_alerts(alert_db, _api_no_discord(alert_db))

    mock_dm.assert_not_called()
    events = await _list_all_events(alert_db)
    assert len(events) == 1
    etype, payload = events[0]
    assert etype == "credit_card.due"
    assert payload == {
        "card_id": card_id,
        "name": "HDFC Regalia",
        "due_date": _FIXED_TODAY.isoformat(),
        "when": "today",
    }
