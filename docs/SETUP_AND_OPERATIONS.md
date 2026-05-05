# Setup and operations

This document covers environment variables, **Phase 6** background jobs, deployment helpers, PDF reports, stocks holdings fields, and related code paths. For day-to-day usage of the app, see the root [README](../README.md).

**Bank statement PDF import** (local parsing, LM Studio fallback, passwords, CLI): see **[BANK_STATEMENT_PARSING.md](BANK_STATEMENT_PARSING.md)**.

## Environment variables (API)

| Variable | Role |
|----------|------|
| `DB_PATH` | SQLite file (shared by API and bot). |
| `DISCORD_BOT_TOKEN` | Bot token (Discord Developer Portal). |
| `DISCORD_USER_ID` | Your user id (for bot command allowlist and **API scheduled DMs**). |
| `DISCORD_DEV_GUILD_ID` | Optional; guild-scoped slash command sync. |
| `SCHEDULER_TIMEZONE` | Default `Asia/Kolkata`; all cron times use this zone. |
| `JOBS_ENABLED` | Default `true`; set `false` to disable APScheduler entirely. |
| `BACKUP_DIR` | Optional; daily **02:00** copy of `DB_PATH` to `finance_backup_YYYY-MM-DD.db`. |
| `API_HOST` / `API_PORT` | Uvicorn bind (see README). |
| `LM_STUDIO_URL` / `LM_STUDIO_MODEL` | Optional; **PDF bank statement** LLM fallback only (local LM Studio). See [BANK_STATEMENT_PARSING.md](BANK_STATEMENT_PARSING.md). |

Copy `.env.example` to `.env` at the repo root. Do not commit real secrets.

## Phase 6 — background jobs (API)

Scheduling is **cron-style** via `register_background_jobs()` in:

`packages/api/src/finance_api/services/background_jobs.py`

This replaced the older **interval-only** investment price sync. Jobs run inside the **API process**; keep the API running (or use systemd / LaunchAgent / Task Scheduler).

Default timezone: **`SCHEDULER_TIMEZONE`** (`Asia/Kolkata` unless overridden).

| When | What |
|------|------|
| Daily **06:00** | Refresh listed investment prices (Yahoo Finance; requires network). |
| Daily **02:00** | Copy SQLite DB to `BACKUP_DIR` (skipped if `BACKUP_DIR` unset). |
| Daily **08:00** | Budget vs actual; **Discord DMs** for categories at **≥75%** or **over** budget (deduplicated state in `settings`). |
| Daily **08:10** | **EMI** reminder DMs when `next_emi_date` is within **3 days**. |
| **Sunday 09:00** | Weekly FY digest (spend, top months, run-rate). |
| **1st of month 08:30** | Previous calendar month spend summary. |
| Daily **18:30** | **Net worth snapshot** from holdings — only on the **last calendar day** of the month. |
| **1 April 00:10** | **FY rollover**: advance `current_fy` and **copy** prior FY budget lines into the new FY. |

### Related code

| Piece | Path |
|-------|------|
| Job registration & handlers | `packages/api/src/finance_api/services/background_jobs.py` |
| Discord REST DMs | `packages/api/src/finance_api/services/discord_notify.py` |
| API settings (`SCHEDULER_TIMEZONE`, `JOBS_ENABLED`, `BACKUP_DIR`, Discord) | `packages/api/src/finance_api/settings.py` |
| App lifespan (scheduler start) | `packages/api/src/finance_api/main.py` |

## PDF report

- **HTTP:** `GET /api/reports/fy-summary.pdf?fy=YYYY-YY` (FY optional; defaults to settings).
- **Implementation:** `packages/api/src/finance_api/services/pdf_report.py` (ReportLab).
- **Dashboard:** Reports page — **Download PDF** (`ReportsPage.tsx`).

## Stocks sub-page and DB fields

- **Columns:** `investments.sector`, `investments.equity_tax_class` (`ltcg` / `stcg` / `unspecified`).
- **Migrations:** `packages/common/src/finance_common/db/migrations.py` (`apply_migrations` after schema bootstrap).
- **UI:** `/investments/stocks` — `dashboard/src/pages/StocksPortfolioPage.tsx` (sector weights, LTCG/STCG tags).

## Setup and deploy polish

| Script / file | Purpose |
|----------------|---------|
| `setup.py` (repo root) | Forwards to `scripts/setup.py`. |
| `scripts/setup.py` | `uv sync`; copy `.env.example` → `.env` if missing. |
| `scripts/expose.py` | `--ngrok --port 8000` or `--tailscale` (prints serve example). |
| `scripts/systemd/finance-api.service` | Example **systemd** unit — edit paths and `EnvironmentFile`. |
| `scripts/launchd/com.personalfinance.api.plist` | Example **macOS LaunchAgent** — edit paths. |
| `scripts/windows/register-api-task.ps1` | Example **Scheduled Task** — edit paths. |

## README and `.env.example`

- Root **README** summarizes architecture and links here for operations detail.
- **`.env.example** documents optional `JOBS_ENABLED`, `SCHEDULER_TIMEZONE`, `BACKUP_DIR`.

## Operational notes

- **Investment price sync** is **daily 06:00**, not `INVESTMENT_SYNC_INTERVAL_MINUTES` (removed in favour of cron).
- Discord DMs require valid **`DISCORD_BOT_TOKEN`** and **`DISCORD_USER_ID`** in the API environment.
- Backups only run when **`BACKUP_DIR`** is set and the API can write to that directory.
