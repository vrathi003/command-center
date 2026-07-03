# Personal Finance OS — CLAUDE.md

## Project Overview

Self-hosted personal finance platform: Discord bot for expense entry → SQLite DB → FastAPI → React dashboard. All local, no cloud services.

**Owner:** Vaibhav
**Spec:** v1.0 (March 2026)
**Current FY:** 2025-26 (April–March, Indian financial year)

---

## Architecture

```
packages/
  common/   → finance-common: shared DB, repositories, types, parsing
  api/      → finance-api: FastAPI server at localhost:8000
  bot/      → finance-bot: Discord bot (expense ingestion)
dashboard/  → React 19 + TypeScript frontend at localhost:3000
scripts/    → migrate_from_excel.py, seed_demo_data.py
tests/      → pytest suite
db/         → SQLite database directory
```

Data flow: Discord message → bot parses → SQLite → FastAPI → React dashboard
Import flow: Bank statement (CSV/XLSX/PDF) → parser → SQLite → dashboard

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Bot | Python 3.14+, discord.py 2.4+, APScheduler 3.10+ |
| API | FastAPI 0.115+, Pydantic 2.10+, aiosqlite 0.20+ |
| Frontend | React 19, TypeScript, Vite, TanStack Query, Recharts, Tailwind CSS 4 |
| DB | SQLite (single file, amounts in paise, FY-aware) |
| LLM | OpenAI-compatible (Ollama/LM Studio local) for PDF bank statement parsing |
| Tooling | uv (Python workspace), ruff, mypy (strict), pytest-asyncio |

---

## Common Commands

```bash
make install       # Install all Python + npm deps
make dev           # Start API + bot
make dev-dashboard # Start React dev server (port 3000)
make seed-demo     # Load demo data into DB
make test          # Run pytest suite
make lint          # ruff + mypy checks
make fmt           # Format with ruff
make migrate       # Import from Excel workbook
make clean         # Remove caches/build artifacts
python start.py    # Start all processes (API + bot)
```

---

## Key Files

| File | Purpose |
|------|---------|
| `packages/common/src/finance_common/db/schema.sql` | SQLite schema — all tables |
| `packages/common/src/finance_common/db/migrations.py` | Runtime schema migrations (ALTER TABLE) |
| `packages/common/src/finance_common/types.py` | Domain enums: Category, PaymentMode, etc. |
| `packages/common/src/finance_common/parsing/` | Expense parser, `account_mentions.py`, `template_line.py`, import/transfer heuristics |
| `packages/common/src/finance_common/parsing/transaction_import.py` | CSV/XLSX row parsing, header normalization, merchant→category heuristics |
| `packages/common/src/finance_common/parsing/bank_statement_pdf.py` | PDF bank statement parser (heuristic + Ollama/LM Studio fallback) |
| `packages/common/src/finance_common/fy.py` | Financial year utilities (April–March) |
| `packages/common/src/finance_common/repositories/` | DB repositories (transactions, accounts, etc.) |
| `packages/api/src/finance_api/main.py` | FastAPI app factory |
| `packages/api/src/finance_api/routers/` | API routers (data domains + `transaction_templates` + health) |
| `packages/api/src/finance_api/services/` | Business logic (dashboard, budget, net worth, import, amortization, PDF reports, etc.) |
| `packages/bot/src/finance_bot/bot.py` | Discord client + slash commands |
| `dashboard/src/pages/` | React routes (dashboard, transactions, transaction templates, accounts, …) |
| `dashboard/src/types/api.ts` | TypeScript API types |
| `.env.example` | Required env vars template |

---

## Data Conventions

- **Amounts:** always stored in **paise** (integer). Display layer divides by 100. Type alias: `Paise`.
- **Dates:** ISO 8601 strings (`YYYY-MM-DD`), no timezone issues.
- **Financial Year:** stored as `'2025-26'`. FY start = April 1, FY end = March 31.
- **Soft deletes:** `is_deleted` flag on transactions — records are never hard-deleted.
- **Audit log:** every change is logged with old/new values and source (`bot` / `dashboard` / `excel_import` / `import`).
- **Transaction types:** `debit`, `credit`, or `transfer` — stored in `transaction_type`. **Transfers** are excluded from spend/budget/dashboard aggregates to avoid double-counting internal moves.

---

## Environment Variables (.env)

```
DISCORD_BOT_TOKEN=
DISCORD_USER_ID=          # Restrict bot to this user ID (optional)
LOCAL_LLM_URL=            # Local LLM for PDF parsing (optional, falls back to heuristic)
DB_PATH=~/finance/finance.db
API_HOST=localhost
API_PORT=8000
APP_ENV=development
LOG_LEVEL=INFO
```

---

## Dashboard Pages (16 routes)

| Page | Route | Purpose |
|------|-------|---------|
| Dashboard | `/` | KPIs (today/week/month spend, income, savings rate, debt, net worth, portfolio), category donut, spend by account |
| Transactions | `/transactions` | Import, manual add drawer (debit/credit/transfer), **Apply template**, filters, bulk delete, ledger |
| Transactions → Templates | `/transactions/templates` | CRUD **transaction templates** (quick-add presets); linked from Transactions hero |
| Budget | `/budget` | Per-category monthly caps, vs-actual utilization bars, rename categories |
| Debt | `/debt` | Loans with EMI, amortization schedules, avalanche/snowball strategies |
| Investments | `/investments` | Market holdings (stocks/MF/ETF) with P&L, fixed income instruments, SIP projector |
| Stocks | `/investments/stocks` | Dedicated stocks sub-page |
| Net Worth | `/net-worth` | Snapshot history (assets − liabilities), line chart, compute from holdings |
| Goals | `/goals` | Savings targets with progress bars, retirement corpus projector |
| Income & Tax | `/income` | Income streams, tax profile (80C/80D), old vs new regime comparison |
| Reports | `/reports` | FY spending by month (bar chart), PDF download |
| Recurring | `/recurring` | Subscriptions and recurring payments (loans + subscriptions) |
| Accounts | `/accounts` | Bank accounts, credit cards, wallets — CRUD with type/institution |
| Credit Cards | `/credit-cards` | CC management, statements, EMI plans |
| Credit Card Detail | `/credit-cards/:cardId` | Individual card details |
| CC Statement | `/credit-cards/:cardId/statements/:statementId` | Statement viewer |
| Settings | `/settings` | FY setting, links to tax config |

---

## API Routers (data + health)

| Router | Key Endpoints |
|--------|--------------|
| `health.py` | `GET /health` (liveness check) |
| `dashboard.py` | `GET /dashboard/summary`, `GET /dashboard/alerts` |
| `transactions.py` | `GET/POST /transactions/`, `POST /transactions/transfer`, `POST /transactions/import`, `POST /transactions/bulk-delete` |
| `transaction_templates.py` | `GET/POST /transaction-templates/`, `PUT/DELETE /transaction-templates/{id}` |
| `accounts.py` | CRUD `/accounts/`, `GET /accounts/types` |
| `budget.py` | `GET /budget/vs-actual`, `PUT /budget/category/{cat}`, `POST /budget/rename-category` |
| `debt.py` | CRUD `/debt/`, `GET /debt/summary`, `GET /debt/{id}/amortization` |
| `investment.py` | CRUD `/investments/`, `GET /investments/portfolio-summary` |
| `fixed_income.py` | CRUD `/fixed-income/`, `GET /fixed-income/summary` |
| `goals.py` | CRUD `/goals/` |
| `net_worth.py` | `GET /net-worth/history`, `POST /net-worth/snapshot` |
| `income.py` | CRUD `/income/`, `GET /income/summary` |
| `reports.py` | `GET /reports/fy-spending`, `GET /reports/fy-summary`, `GET /reports/fy-summary.pdf` |
| `subscriptions.py` | CRUD `/subscriptions/` |
| `credit_cards.py` | CRUD `/credit-cards/`, statements, EMI plans |
| `settings.py` | `GET /settings/`, `PUT /settings/` |

---

## Transaction templates — how to use

1. **Define presets** — Dashboard → **Transactions** → **Templates** (`/transactions/templates`). At minimum set a **name**; optional defaults: amount (paise), category, merchant, payment mode, account, type (debit / credit / transfer), notes, tags.
2. **Apply in the drawer** — **Transactions** → **Add transaction** → **Apply template** → adjust date/amount → **Save**. Transfer templates set **from** account from the template; choose **to** before saving.
3. **Discord** — Use **`template <name>`** or **`t <name>`** inside `/log` or after `log ` (e.g. `log template Netflix 500`). Name matching is longest-prefix first, then fuzzy. Remainder text supplies amount/date (debit/credit) or transfer destination phrase. Ambiguous accounts may use **1️⃣–4️⃣** reactions; **5️⃣** skips.

---

## Bank Statement Import Pipeline

1. Upload file (CSV/XLSX/XLS/PDF) via `POST /transactions/import`
2. **PDF:** PyMuPDF text extraction → heuristic line parser → Ollama/LM Studio fallback (if configured)
3. **CSV/XLSX:** pandas read → auto-detect header row (skip bank preamble) → normalize headers
4. Header normalization: `normalize_header_key()` maps 50+ aliases to canonical fields (date, amount, merchant, etc.)
5. Debit/credit detection: separate columns or single amount column; `transaction_type` inferred
6. Merchant→category heuristics: `_MERCHANT_CATEGORY_HINTS` (50+ keyword→Category mappings)
7. Payment mode auto-detection: UPI/NEFT/ATM patterns in merchant string
8. Optional: tag all rows to a specific account via `account_name` form field
9. Insert into `transactions` table with `source = 'import'`

---

## Implementation Status

### ✅ Done
- SQLite schema: `transactions` (with `account_id`, `transfer_pair_id`, `tags`), `transaction_templates`, plus accounts, budgets, debts, investments, assets, insurance, home, …
- API: transactions (create, transfer pair, import, bulk-delete), **transaction-templates CRUD**, accounts, budgets, …
- Discord bot: NL expenses, **transfers** (`try_parse_transfer_line`), **account fuzzy** + reaction picker, **`template` / `t` template expansion**, `/log`, `/edit`, `/undo`, `/balance`, `/budget`, `/debt`, `/goal`, `/net-worth`, `/report`, `/finance_help`
- React dashboard: transactions page (drawer, template apply), **templates page**, import, filters, …
- FY-aware date handling throughout
- Expense parser (regex + LLM fallback for PDFs)
- Merchant→category mapping (54 keyword→category heuristic rules)
- Amortization calculations (reducing-balance schedule)
- Excel migration script (`migrate_from_excel.py`)
- Demo data seeder
- Smart bank statement parser (CSV/XLSX/PDF with auto header detection, preamble skip, 44+ header aliases)
- Debit/credit transaction type detection and display (CR/DR badges)
- Multi-account support (account tagging on import, account filter on transactions)
- Category + transaction type filters on Transactions page (multi-select pills with counts)
- Date range presets (this month, last month, last 3/6 months, this FY, all time) + custom date pickers
- Bulk delete on Transactions page (soft-delete with confirmation)
- Spend-by-account breakdown on Dashboard
- SIP step-up projector on Investments page (monthly, step-up %, years, CAGR)
- Avalanche vs Snowball debt strategies on Debt page (sorted strategy cards)
- Old/New tax regime comparison on Income page (side-by-side with slab estimates)
- 80C/80D deduction inputs saved to settings
- Retirement corpus projector on Goals page (with localStorage persistence)
- Accounts page (full CRUD — savings, current, CC, wallet, investment, loan, other)
- Recurring Payments page (subscriptions CRUD + loan EMIs view)
- Credit Cards page (cards CRUD, detail view, statement uploads, EMI plans)
- Stocks portfolio sub-page (`/investments/stocks`)
- FY reports with PDF download (`GET /reports/fy-summary.pdf`)
- Payment mode auto-detection (UPI/NEFT/ATM from merchant narration)

### ✅ Also Done (updated after audit vs latest GitHub)
- **Investment price sync** — `investment_sync.py` via `yfinance` (Yahoo Finance), registered as daily 6AM APScheduler job in `background_jobs.py`
- **All 8 background jobs** — `background_jobs.py`: price sync 6AM, DB backup 2AM, budget alerts 8AM (Discord DMs at 75% + over-budget), EMI reminders 8:10AM (3 days before due), weekly Discord digest Sunday 9AM, monthly summary 1st, month-end NW snapshot, FY rollover April 1
- **Proactive Discord DMs** — budget/EMI alerts send to configured `DISCORD_USER_ID` with deduplication via `settings` JSON state
- **Auto-start scripts** — `scripts/launchd/com.personalfinance.api.plist` (macOS), `scripts/systemd/finance-{api,bot,dashboard}.service` (Linux), `scripts/windows/register-api-task.ps1`
- **`setup.py`** and **`expose.py`** — one-click setup and ngrok/Tailscale tunnel helper both in `scripts/`
- **Edit individual transactions** — `PUT /transactions/{id}` (`update_transaction`) handles debit/credit edits and transfer pair re-linking; dashboard drawer has `editDraft` state
- **Assets module** — `AssetsPage.tsx` (425 lines) + `AssetDetailPage.tsx` + `assets.py` router — real estate / vehicle tracking beyond original spec
- **Beyond-spec pages** — `InsurancePage.tsx` (685 lines), `HomeInventoryPage.tsx` (359 lines), `JournalPage.tsx` (238 lines)

### ❌ Remaining Gaps (within spec)

#### High Priority
1. **Duplicate detection on import** — Same date + amount + merchant within ±1 day = warn/skip; prevents re-uploading same statement
2. **Text search on transactions** — Search by merchant name across the full ledger
3. **Copy budgets to new FY** — FY rollover job copies budgets but UI has no "Copy from last FY" button for manual use
4. **Database backup download** — No download of SQLite / JSON dump from Settings page; only file-system backup via job

#### Financial Intelligence
5. **XIRR on investments** — True annualized return; current P&L shows absolute gain only
6. **Full tax computation** — Slab-wise breakdown with exact rupee amounts; HRA exemption calculator; advance tax dates (current Income page shows illustrative estimate only)
7. **Prepayment / rate-change calculator** on Debt page
8. **Capital gains calculator** — LTCG/STCG classification by holding period on Stocks sub-page
9. **Asset allocation view** — Equity vs debt vs real estate vs gold pie + rebalancing

#### Medium Priority (not yet done)
- **Payoff timeline chart** on Debt page — horizontal bar showing when each loan closes (spec §6.3)
- **Debt-to-income gauge** with safe/caution/danger thresholds (spec §6.3)
- **Sector weightings + rebalancing** on Stocks sub-page (spec §6.4)
- **FD/RD maturity ladder** timeline view on Investments page (spec §6.4)
- **Category-wise annual comparison** in Reports — "Food: ₹1.2L this FY vs ₹95K last FY"
- **Top merchants report** — total spend ranked by merchant
- **Income vs expense trend** — monthly line chart showing savings gap
- **CSV export** of transactions and all data
- **Net worth breakdown by asset class** — liquid, semi-liquid, illiquid, retirement
- **Month-over-month change** on Net Worth page
- **Time-to-goal projection** on Goals page
- **Emergency fund goal** (auto-calculated from 6× monthly expenses)
- **Part-payment history** + **interest certificate tracking** (Section 24b) on Debt page
- **Dividend/interest income tracking** on Investments page

### Build Phases (Spec §11 + extensions) — updated 2026-07-02
| Phase | Status |
|-------|--------|
| 1 — Core bot | ✅ Done |
| 2 — API + basic dashboard | ✅ Done (transactions + templates APIs, dashboard routes) |
| 3 — Debt & investments | ✅ Done (amortization, SIP projector, avalanche/snowball, stocks sub-page, price sync via yfinance) |
| 4 — Net worth & goals | ✅ Done (snapshots, retirement projector) |
| 5 — Income & tax | ✅ Page done (regime comparison, 80C/80D); full slab computation ❌ |
| 6 — Reports & automation | ✅ Done (all 8 APScheduler jobs, Discord DMs, FY rollover, DB backup) |
| 7 — Excel migration | ✅ Script exists |
| 8 — Bank statement import | ✅ CSV/XLSX/PDF with smart parsing, 44+ header aliases, 54 merchant rules |
| 9 — Multi-account | ✅ Account CRUD + import tagging + filters + dashboard breakdown |
| 10 — Credit cards & recurring | ✅ Cards CRUD, statements, EMI plans, subscriptions page |
| 11 — Assets module | ✅ AssetsPage + AssetDetailPage + assets router (beyond original spec scope) |
| 12 — Beyond spec | ✅ Insurance, Home Inventory, Journal pages; single-tx edit; setup.py; expose.py; autostart scripts |
