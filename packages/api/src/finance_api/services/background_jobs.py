"""Scheduled jobs: prices, budgets, EMI, Discord digests, FY rollover, backups."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from finance_api.services.debt_emi import auto_advance_active_debts
from finance_api.services.budget_service import build_vs_actual
from finance_api.services.cc_statement_fetch import fetch_cc_statements
from finance_api.services.discord_notify import send_discord_dm
from finance_api.services.gmail_sync import sync_gmail_transactions
from finance_api.services.investment_sync import sync_investment_prices
from finance_api.services.net_worth_service import compute_totals_from_holdings
from finance_api.settings import ApiSettings
from finance_common.db import open_db
from finance_common.fy import date_to_fy
from finance_common.reports_fy import build_fy_spending, build_fy_summary
from finance_common.repositories import budgets as budget_repo
from finance_common.repositories import credit_cards as cc_repo
from finance_common.repositories import debts as debt_repo
from finance_common.repositories import net_worth as nw_repo
from finance_common.repositories import settings_repo
from finance_common.repositories import transactions as tx_repo

logger = logging.getLogger(__name__)


def _rupees(paise: int) -> str:
    return f"₹{paise / 100:,.2f}"


async def _load_json_state(conn: aiosqlite.Connection, key: str) -> dict[str, str]:
    raw = await settings_repo.get_value(conn, key)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        return {}


async def _save_json_state(conn: aiosqlite.Connection, key: str, state: dict[str, str]) -> None:
    if len(state) > 200:
        items = list(state.items())[-150:]
        state = dict(items)
    await settings_repo.set_value(conn, key, json.dumps(state))


async def job_price_sync_6am(db_path: Path) -> None:
    async with open_db(db_path) as conn:
        n = await sync_investment_prices(conn)
        logger.info("Scheduled price sync: %s holding(s) updated", n)


async def job_backup_2am(db_path: Path, backup_dir: Path | None) -> None:
    if backup_dir is None:
        logger.debug("BACKUP_DIR not set — skipping DB backup")
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"finance_backup_{date.today().isoformat()}.db"
    try:
        shutil.copy2(db_path, dest)
        logger.info("Database backup: %s", dest)
    except OSError:
        logger.exception("Database backup failed")


async def job_budget_and_alerts(db_path: Path, api: ApiSettings) -> None:
    """8:00 — budget vs actual scan + 75% / over-budget Discord DMs."""
    token = api.discord_bot_token
    uid = api.discord_user_id
    async with open_db(db_path) as conn:
        today = date.today()
        fy = await settings_repo.get_current_fy(conn)
        _, rows = await build_vs_actual(conn, fy=str(fy), year=today.year, month=today.month)
        ym = f"{today.year:04d}-{today.month:02d}"
        state = await _load_json_state(conn, "job_budget_dm_state")
        lines: list[str] = []
        for row in rows:
            if row.status not in ("warn", "over"):
                continue
            if row.budget_paise is None or row.budget_paise <= 0:
                continue
            key = f"{ym}|{row.category}"
            prev = state.get(key)
            if row.status == "warn" and prev is None:
                pct = (row.pct_of_budget or 0) * 100
                lines.append(
                    f"**Budget 75%+** · {row.category}: spent {_rupees(row.spent_paise)} / "
                    f"budget {_rupees(row.budget_paise)} (~{pct:.0f}%)",
                )
                state[key] = "warn"
            elif row.status == "over" and prev != "over":
                lines.append(
                    f"**Over budget** · {row.category}: spent {_rupees(row.spent_paise)} vs "
                    f"budget {_rupees(row.budget_paise)}",
                )
                state[key] = "over"
        await _save_json_state(conn, "job_budget_dm_state", state)

    if not lines or not token or not uid:
        if lines and (not token or not uid):
            logger.info("Budget alerts skipped (Discord not configured): %s", len(lines))
        return
    body = "**Finance OS — budget check**\n" + "\n".join(lines[:25])
    await send_discord_dm(bot_token=token, user_id=uid, content=body)


async def job_emi_reminders(db_path: Path, api: ApiSettings) -> None:
    token = api.discord_bot_token
    uid = api.discord_user_id
    async with open_db(db_path) as conn:
        debts = await debt_repo.list_debts(conn, status="active")
        today = date.today()
        state = await _load_json_state(conn, "job_emi_dm_state")
        msgs: list[str] = []
        for d in debts:
            if not d.next_emi_date:
                continue
            try:
                due = date.fromisoformat(d.next_emi_date)
            except ValueError:
                continue
            delta = (due - today).days
            if not (0 <= delta <= 3):
                continue
            key = f"emi|{d.id}|{d.next_emi_date}"
            if state.get(key):
                continue
            state[key] = "1"
            when = "today" if delta == 0 else f"in {delta} day(s)"
            msgs.append(f"**EMI** · {d.name}: due {when} ({d.next_emi_date})")
        await _save_json_state(conn, "job_emi_dm_state", state)

    if not msgs or not token or not uid:
        return
    await send_discord_dm(
        bot_token=token,
        user_id=uid,
        content="**Finance OS — EMI reminder**\n" + "\n".join(msgs[:20]),
    )


async def job_cc_due_date_alerts(db_path: Path, api: ApiSettings) -> None:
    """Daily 8:05 AM — alert when a CC bill is due today or tomorrow."""
    token = api.discord_bot_token
    uid = api.discord_user_id
    if not token or not uid:
        return
    today = date.today()
    tomorrow = today + timedelta(days=1)
    async with open_db(db_path) as conn:
        cards = await cc_repo.list_credit_cards(conn, active_only=True)
        state = await _load_json_state(conn, "job_cc_due_state")
        msgs: list[str] = []
        for card in cards:
            if card.due_day is None:
                continue
            for check_date in (today, tomorrow):
                if check_date.day != card.due_day:
                    continue
                due_str = check_date.isoformat()
                key = f"cc_due|{card.id}|{due_str}"
                if state.get(key):
                    continue
                state[key] = "1"
                # Get live balance if linked
                live_bal_str = ""
                if card.account_id is not None:
                    bal = await tx_repo.cc_live_balance(conn, card.account_id)
                    if bal > 0:
                        live_bal_str = f" — outstanding {_rupees(bal)}"
                when = "today" if check_date == today else "tomorrow"
                msgs.append(f"**{card.name}** bill due {when} ({due_str}){live_bal_str}")
        await _save_json_state(conn, "job_cc_due_state", state)

    if not msgs:
        return
    await send_discord_dm(
        bot_token=token,
        user_id=uid,
        content="**Finance OS — CC bill due**\n" + "\n".join(msgs[:10]),
    )


async def job_weekly_discord(db_path: Path, api: ApiSettings) -> None:
    token = api.discord_bot_token
    uid = api.discord_user_id
    if not token or not uid:
        return
    async with open_db(db_path) as conn:
        fy = await settings_repo.get_current_fy(conn)
        fy_s, spend_rows, total = await build_fy_spending(conn, fy)
        top = sorted(spend_rows, key=lambda r: int(r["spent_paise"]), reverse=True)[:4]
        parts = [
            "**Finance OS — weekly digest**",
            f"FY **{fy_s}** · FY spend to date: {_rupees(total)}",
            "",
            "Top FY months by spend:",
        ]
        for r in top:
            parts.append(f"· {r['label']}: {_rupees(int(r['spent_paise']))}")
        _, _, run_rate, implied = await build_fy_summary(conn, fy)
        parts.extend(
            [
                "",
                f"Run-rate income (annual est.): {_rupees(run_rate)}",
                f"Implied savings vs FY spend: {_rupees(implied)}",
            ],
        )
    await send_discord_dm(bot_token=token, user_id=uid, content="\n".join(parts))


async def job_monthly_discord(db_path: Path, api: ApiSettings) -> None:
    """Runs on calendar day 1 — previous month summary."""
    token = api.discord_bot_token
    uid = api.discord_user_id
    if not token or not uid:
        return
    last_eom = date.today() - timedelta(days=1)
    y, m = last_eom.year, last_eom.month
    async with open_db(db_path) as conn:
        fy = await settings_repo.get_current_fy(conn)
        _, rows = await build_vs_actual(conn, fy=str(fy), year=y, month=m)
        spent_total = sum(r.spent_paise for r in rows)
        over_cats = [r.category for r in rows if r.status == "over"]
        label = f"{y:04d}-{m:02d}"
        lines = [
            "**Finance OS — monthly summary**",
            f"Calendar month **{label}**",
            f"Total spend: {_rupees(spent_total)}",
        ]
        if over_cats:
            lines.append("Over budget: " + ", ".join(over_cats[:15]))
    await send_discord_dm(bot_token=token, user_id=uid, content="\n".join(lines))


async def job_month_end_net_worth(db_path: Path) -> None:
    """Evening on last calendar day of month — snapshot from holdings."""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    if tomorrow.month == today.month:
        return
    async with open_db(db_path) as conn:
        assets, liabilities, _ = await compute_totals_from_holdings(conn)
        await nw_repo.upsert_snapshot(
            conn,
            snapshot_date=today.isoformat(),
            total_assets_paise=assets,
            total_liabilities_paise=liabilities,
        )
        logger.info("Month-end net worth snapshot for %s", today.isoformat())


async def job_gmail_sync(db_path: Path, api: ApiSettings) -> None:
    """Every 3 hours — fetch new financial emails and insert to staging table."""
    if not api.gmail_credentials_path or not api.gmail_credentials_path.exists():
        return
    async with open_db(db_path) as conn:
        n = await sync_gmail_transactions(
            conn,
            api.gmail_credentials_path,
            api.gmail_token_path,
            api.gmail_sync_lookback_hours,
        )
        if n:
            logger.info("Gmail sync: %s new staged transaction(s)", n)


async def job_fetch_cc_statements(db_path: Path, api: ApiSettings) -> None:
    """Daily — auto-fetch credit-card statement PDF attachments from Gmail for any card
    with auto_fetch_enabled=1. Statements always land as pending_review; never applied."""
    if not api.gmail_credentials_path or not api.gmail_credentials_path.exists():
        return
    async with open_db(db_path) as conn:
        counts = await fetch_cc_statements(conn, api.gmail_credentials_path, api.gmail_token_path)
        if counts["staged"]:
            logger.info(
                "CC statement auto-fetch: %s new statement(s) staged (skipped: %s unmatched, "
                "%s duplicate)",
                counts["staged"],
                counts["skipped_unmatched"],
                counts["skipped_duplicate"],
            )


async def job_emi_auto_advance(db_path: Path) -> None:
    """Daily 9:00 AM — reduce balance and advance next_emi_date for all active debts."""
    async with open_db(db_path) as conn:
        updated = await auto_advance_active_debts(conn)
        if updated:
            logger.info("EMI auto-advance: %s debt(s) updated", updated)


async def job_fy_rollover_april_first(db_path: Path) -> None:
    today = date.today()
    if not (today.month == 4 and today.day == 1):
        return
    expected = date_to_fy(today)
    async with open_db(db_path) as conn:
        current = await settings_repo.get_current_fy(conn)
        if str(current) == str(expected):
            logger.info("FY already at %s — rollover skipped", expected)
            return
        rows = await budget_repo.effective_budgets_for_fy(conn, str(current))
        await settings_repo.set_value(conn, "current_fy", str(expected))
        april_first = date(today.year, 4, 1)
        for r in rows:
            await budget_repo.set_monthly_budget(
                conn,
                category=r.category,
                fy_year=str(expected),
                monthly_amount_paise=r.monthly_amount_paise,
                effective_from=april_first,
            )
        logger.info("FY rollover: %s → %s (%s categories)", current, expected, len(rows))


def register_background_jobs(scheduler: AsyncIOScheduler, api: ApiSettings) -> None:
    """Register cron triggers (times in ``api.scheduler_timezone``)."""
    if not api.jobs_enabled:
        logger.info("JOBS_ENABLED=false — no scheduled jobs")
        return
    tz = api.scheduler_timezone
    try:
        ZoneInfo(tz)
    except Exception:
        logger.warning("Invalid SCHEDULER_TIMEZONE %r — using Asia/Kolkata", tz)
        tz = "Asia/Kolkata"

    db_path = api.db_path

    def trig(**kw: object) -> CronTrigger:
        return CronTrigger(timezone=tz, **kw)

    common = {"replace_existing": True, "max_instances": 1, "coalesce": True}

    scheduler.add_job(
        job_price_sync_6am,
        trig(hour=6, minute=0),
        args=[db_path],
        id="prices_6am",
        **common,
    )
    scheduler.add_job(
        job_backup_2am,
        trig(hour=2, minute=0),
        args=[db_path, api.backup_dir],
        id="backup_2am",
        **common,
    )
    scheduler.add_job(
        job_budget_and_alerts,
        trig(hour=8, minute=0),
        args=[db_path, api],
        id="budget_8am",
        **common,
    )
    scheduler.add_job(
        job_emi_reminders,
        trig(hour=8, minute=10),
        args=[db_path, api],
        id="emi_reminders",
        **common,
    )
    scheduler.add_job(
        job_weekly_discord,
        trig(day_of_week=6, hour=9, minute=0),
        args=[db_path, api],
        id="weekly_discord_sun",
        **common,
    )
    scheduler.add_job(
        job_monthly_discord,
        trig(day=1, hour=8, minute=30),
        args=[db_path, api],
        id="monthly_summary_1st",
        **common,
    )
    scheduler.add_job(
        job_month_end_net_worth,
        trig(hour=18, minute=30),
        args=[db_path],
        id="nw_month_end",
        **common,
    )
    scheduler.add_job(
        job_fy_rollover_april_first,
        trig(month=4, day=1, hour=0, minute=10),
        args=[db_path],
        id="fy_rollover_apr1",
        **common,
    )
    scheduler.add_job(
        job_emi_auto_advance,
        trig(hour=9, minute=0),
        args=[db_path],
        id="emi_auto_advance_9am",
        **common,
    )
    scheduler.add_job(
        job_cc_due_date_alerts,
        trig(hour=8, minute=5),
        args=[db_path, api],
        id="cc_due_alerts_8am",
        **common,
    )
    scheduler.add_job(
        job_gmail_sync,
        IntervalTrigger(hours=3, timezone=tz),
        args=[db_path, api],
        id="gmail_sync_3h",
        **common,
    )
    scheduler.add_job(
        job_fetch_cc_statements,
        trig(hour=7, minute=0),
        args=[db_path, api],
        id="cc_statement_fetch_7am",
        **common,
    )
    logger.info(
        "Registered background jobs (timezone=%s, backup_dir=%s, gmail=%s)",
        tz,
        api.backup_dir,
        "enabled" if api.gmail_credentials_path else "disabled (GMAIL_CREDENTIALS_PATH not set)",
    )
