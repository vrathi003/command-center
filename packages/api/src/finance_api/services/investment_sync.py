"""Background refresh of market prices for holdings (Yahoo Finance tickers)."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime

import aiosqlite

from finance_common.repositories import investments as inv_repo

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yfinance")


def _fetch_yahoo_close_inr(ticker: str) -> float | None:
    """Return last close price in INR (or quote currency); None if unavailable."""
    try:
        import yfinance as yf  # noqa: PLC0415 — optional heavy import
    except ImportError:
        return None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist is None or hist.empty:
            return None
        close = float(hist["Close"].iloc[-1])
        return close if close > 0 else None
    except Exception:
        return None


def _normalise_ticker(instrument: str) -> str:
    s = instrument.strip()
    if not s:
        return s
    upper = s.upper()
    if "." in upper or "=" in upper:
        return s.strip()
    # Default NSE suffix for bare symbols (user can pass RELIANCE.NS explicitly)
    return f"{upper}.NS"


async def sync_investment_prices(conn: aiosqlite.Connection) -> int:
    """Set ``current_price_paise`` and ``last_synced`` from Yahoo where a price is fetched."""
    rows = await inv_repo.list_investments(conn)
    updated = 0
    now = datetime.now(tz=UTC).replace(microsecond=0).isoformat()
    loop = asyncio.get_running_loop()

    for row in rows:
        if row.units is None or row.units <= 0:
            continue
        ticker = _normalise_ticker(row.instrument)
        if not ticker:
            continue
        price = await loop.run_in_executor(_executor, _fetch_yahoo_close_inr, ticker)
        if price is None:
            continue
        paise = int(round(price * 100))
        if paise <= 0:
            continue
        new_row = replace(row, current_price_paise=paise, last_synced=now)
        await inv_repo.update_investment_row(conn, new_row)
        updated += 1
    return updated
