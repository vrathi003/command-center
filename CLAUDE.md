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
| LLM | OpenAI-compatible (LM Studio local) for PDF bank statement parsing |
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
| `packages/common/src/finance_common/parsing/bank_statement_pdf.py` | PDF bank statement parser (heuristic + LM Studio fallback) |
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
LM_STUDIO_URL=            # Local LLM for PDF parsing (optional, falls back to heuristic)
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
2. **PDF:** PyMuPDF text extraction → heuristic line parser → LM Studio fallback (if configured)
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

### 🚧 Partially Done / Needs Verification
- **Investment price sync** (NSE/BSE, AMFI NAV) — APScheduler installed but jobs not implemented

### ❌ Not Yet Done — Priority Roadmap

#### High Priority (Quality of Life)
1. **Edit individual transactions** — Currently can only bulk delete, no way to fix wrong category/amount/date on a single transaction
2. **Duplicate detection on import** — Same date + amount + merchant within ±1 day = warn/skip; prevents re-uploading same statement
3. **Text search on transactions** — Search by merchant name across the full ledger
4. **Copy budgets to new FY** — When FY rolls over (April 1), all budgets are gone; need "Copy from last FY" button
5. **Database backup download** — Download SQLite file or JSON dump from Settings page; single-machine data = single point of failure

#### High Priority (Financial Intelligence)
6. **Assets module** — Track real estate (apartments with PSF, area, total cost breakdown, possession dates, milestone payments, linked loans with disbursement tracking, pre-EMI vs full EMI, capital gains on sale) and vehicles (purchase price, depreciation); feeds into Net Worth
7. **XIRR on investments** — True annualized return accounting for investment timing; current P&L shows absolute gain but not rate of return
8. **Prepayment calculator on Debt page** — "If I pay ₹5L extra, how much interest saved and months reduced?"; includes rate change simulator for floating-rate loans
9. **Full tax computation (both regimes)** — Slab-wise breakdown: Gross → deductions → taxable income → tax payable; side-by-side Old vs New regime with exact rupee amounts; HRA exemption calculator; advance tax dates

#### Medium Priority (Not Yet Done)
- **Capital gains calculator** — Indexed cost of acquisition, LTCG/STCG classification by holding period, integration with Income & Tax page
- **Asset allocation view** — Pie chart: equity vs debt vs real estate vs gold; rebalancing suggestions
- **Category-wise annual comparison** in Reports — "Food: ₹1.2L this FY vs ₹95K last FY (+26%)"
- **Top merchants report** — Where money actually goes, ranked by total spend
- **Income vs expense trend** — Monthly line chart showing savings gap
- **CSV export** of transactions and all data
- **Net worth breakdown by asset class** — Liquid, semi-liquid, illiquid, retirement
- **Month-over-month change** on Net Worth page
- **Time-to-goal projection** on Goals page
- **Emergency fund goal** (auto-calculated from 6× monthly expenses)
- **Part-payment history** on Debt page
- **Interest certificate tracking** (Section 24b) on Debt page
- **Dividend/interest income tracking** on Investments page

#### Lower Priority (Spec items, not yet done)
- **Background jobs** (APScheduler): price sync, budget alerts, EMI reminders, weekly/monthly Discord reports, NW snapshots, FY rollover, DB backup
- **Proactive Discord DMs:** budget alerts at 75%, over-budget DMs, EMI reminders 3 days before
- **Auto-start scripts:** launchd plist (macOS), Task Scheduler XML (Windows), systemd unit (Linux)
- **`setup.py`** one-click setup script
- **`expose.py`** ngrok/Tailscale tunnel helper

### Build Phases (Spec §11 + extensions)
| Phase | Status |
|-------|--------|
| 1 — Core bot | ✅ Done |
| 2 — API + basic dashboard | ✅ Done (transactions + templates APIs, dashboard routes) |
| 3 — Debt & investments | ✅ Done (amortization, SIP projector, avalanche/snowball, stocks sub-page); price sync 🚧 |
| 4 — Net worth & goals | ✅ Done (snapshots, retirement projector) |
| 5 — Income & tax | ✅ Page done (regime comparison, 80C/80D); full slab computation ❌ |
| 6 — Reports & automation | 🚧 Reports + PDF download done; background jobs ❌ |
| 7 — Excel migration | ✅ Script exists |
| 8 — Bank statement import | ✅ CSV/XLSX/PDF with smart parsing, 44+ header aliases, 54 merchant rules |
| 9 — Multi-account | ✅ Account CRUD + import tagging + filters + dashboard breakdown |
| 10 — Credit cards & recurring | ✅ Cards CRUD, statements, EMI plans, subscriptions page |
| 11 — Assets module | ❌ Not started |
