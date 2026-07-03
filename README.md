# Personal Finance OS

A fully self-hosted personal finance platform built for the Indian financial year (April–March). Log expenses via Discord, import bank statements, track loans and investments, and view everything in a React dashboard — all running locally, no cloud services required.

---

## Architecture

```
packages/
  common/   → Shared DB schema, repositories, parsing utilities
  api/      → FastAPI server  (localhost:8000)
  bot/      → Discord bot for expense entry
dashboard/  → React 19 + TypeScript frontend  (localhost:3000)
scripts/    → Data migration and utility scripts
tests/      → pytest suite
db/         → SQLite database
```

**Data flow:** Discord message → bot parses → SQLite → FastAPI → React dashboard
**Import flow:** Bank statement (CSV / XLSX / PDF) → smart parser → SQLite → dashboard

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot | Python 3.14+, discord.py 2.4+, APScheduler 3.10+ |
| API | FastAPI 0.115+, Pydantic 2.10+, aiosqlite 0.20+ |
| Frontend | React 19, TypeScript, Vite, TanStack Query, Recharts, Tailwind CSS 4 |
| Database | SQLite — amounts stored in paise (integer), FY-aware |
| LLM (optional) | OpenAI-compatible local server (Ollama/LM Studio) for PDF parsing |
| Tooling | uv (Python workspace), ruff, mypy strict, pytest-asyncio |

---

## Quick Start

### 1 — Prerequisites

- Python 3.14+ with [uv](https://docs.astral.sh/uv/) — `curl -Lsf https://astral.sh/uv/install.sh | sh`
- Node.js 20+
- A Discord bot token ([create one here](https://discord.com/developers/applications)) — enable **Message Content Intent** under Bot → Privileged Gateway Intents

### 2 — Install dependencies

```bash
make install
```

### 3 — Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_USER_ID=your_discord_user_id   # right-click your name in Discord → Copy User ID
DB_PATH=~/finance/finance.db

# API defaults (change if needed)
API_HOST=127.0.0.1
API_PORT=8000
APP_ENV=development

# Optional — AI-powered PDF bank statement parsing (heuristic parsing always runs first)
LOCAL_LLM_ENABLED=true
LOCAL_LLM_URL=http://localhost:1234/v1
LOCAL_LLM_MODEL=qwen2.5:1.5b
LOCAL_LLM_TIMEOUT_SECONDS=600
```

### 4 — Load demo data (optional)

```bash
make seed-demo
```

### 5 — Start everything

```bash
make dev            # starts API server + Discord bot
make dev-dashboard  # in a separate terminal — starts React dev server
```

Open **http://localhost:3000** in your browser.
API docs (Swagger UI): **http://localhost:8000/docs**

---

## All Commands

| Command | Description |
|---|---|
| `make install` | Install all Python + npm dependencies |
| `make dev` | Start API server + Discord bot |
| `make dev-dashboard` | Start React dev server on port 3000 |
| `make seed-demo` | Seed the database with demo data |
| `make test` | Run the full pytest suite |
| `make lint` | ruff + mypy checks |
| `make fmt` | Format with ruff |
| `make migrate` | Import historical data from an Excel workbook |
| `make migrate-dry` | Dry-run the Excel migration (no DB writes) |
| `make pdf-to-csv PDF=~/dl/stmt.pdf OUT=~/dl/out.csv` | Convert a bank statement PDF to CSV |
| `make clean` | Remove caches, build artifacts, dist folder |

---

## Features

### Dashboard (`/`)

The home screen shows a live snapshot of your finances, auto-refreshing every 30 seconds.

- **KPI tiles** — today's spend, this-week spend, this-month spend, monthly income, savings rate, total debt outstanding, and portfolio value
- **Category donut chart** — current month's spending broken down by category
- **Spend by account** — which bank account or card you're spending from most
- **Alerts** — budget over-limit warnings, upcoming EMIs, and other nudges

---

### Transactions (`/transactions`)

Your complete financial ledger with powerful import and filtering.

#### Manual entry (Add transaction)

Open **Add transaction** to slide in a form from the right:

- **Debit / Credit / Transfer** — transfers create two linked rows with a shared pair id; they are **excluded from spend totals** (so moving money between your own accounts does not inflate expenses or income).
- **Apply template** — pick a saved preset to fill category, merchant, payment mode, account, notes, tags, and amount (when set on the template). Edit anything before saving. Manage presets on **Transactions → Templates** (`/transactions/templates`).

#### Importing bank statements

1. Click **Import** and upload a CSV, XLSX, XLS, or PDF file
2. The parser **auto-detects and skips bank preamble rows** (account number blocks, statement date headers, blank rows, trailing disclaimers) — works with HDFC, SBI, ICICI, Axis, and most Indian bank formats without any configuration
3. Optionally tag all imported rows to a specific account using the **Account** dropdown
4. Debit / Credit is auto-detected from column names or amount sign; **CR / DR badges** appear on each row
5. **54 merchant→category heuristic rules** auto-classify common merchants (Swiggy, Zomato, Amazon, Uber, NEFT patterns, ATM withdrawals, and more)
6. Payment mode (UPI / NEFT / ATM / cheque) is auto-detected from the narration string

**Supported column name aliases (44+):**
`Date`, `Txn Date`, `Value Date`, `Transaction Date`, `Narration`, `Description`, `Particulars`, `Cheque No`, `Debit`, `Withdrawal Amt`, `Credit`, `Deposit Amt`, `Balance`, `Closing Balance`, and many more — any of these map automatically to the correct field.

#### Filters

- **Date range** — presets: This Month, Last Month, Last 3 Months, Last 6 Months, This FY, All Time; or a custom date picker
- **Category** — multi-select pills with live transaction counts
- **Transaction type** — Debit / Credit toggle pills
- **Account** — filter to a single bank account or card

#### Bulk delete

Select any rows with the checkbox column and soft-delete in one click (records are flagged `is_deleted`, never hard-deleted from the database).

---

### Transaction templates (`/transactions/templates`)

Save **quick-add presets** for recurring or repetitive lines (rent, subscriptions, typical transfers). Each template can store: name, optional default amount (paise), merchant, category, default account, payment mode, transaction type (debit / credit / transfer), notes, and tags.

#### How to use templates

1. **Create or edit** — Go to **Transactions** → **Templates** (or open `/transactions/templates`). Add a row with at least a **name**; fill other fields as defaults.
2. **From the Add transaction drawer** — Click **Add transaction** on the Transactions page, choose a template in **Apply template**, adjust date/amount if needed, then **Save**.
3. **From Discord** — Prefix your `/log` or `log …` text with **`template `** or **`t `**, then the template name (longest name match wins), then optional extra text for amount/date:
   - `template Netflix 500`
   - `t rent yesterday`
   - `log template monthly rent 25000`
   - **Transfer templates** — The template’s **account** is treated as the **from** account; add a normal transfer phrase after the name (e.g. `template MyXfer 5000 to icici`) or a destination label; the bot may ask you to pick accounts with **1–5** reactions if a name is ambiguous.

---

### Budget (`/budget`)

Set monthly spending caps per category and track actual vs budgeted.

- **Utilization bars** — colour-coded progress bars that shift green → yellow → red as you approach and exceed the cap
- **Rename categories** — consolidate aliases (e.g. "Food & Dining" → "Food") — updates budgets, transactions, merchant rules, and goals in a single operation
- Budgets are FY-aware; the cap set for a category applies every month of that financial year

---

### Debt (`/debt`)

Full loan lifecycle management — from the day you sign to the final EMI.

#### Adding a loan

Fill in the **Add debt** form at the bottom of the page:

| Field | Notes |
|---|---|
| Name | Free-text label for the loan |
| Lender | Bank or NBFC name |
| Type | Home Loan, Car Loan, Personal Loan, Credit Card EMI, Education Loan, etc. |
| Sanctioned amount | Original principal (₹) |
| Current balance | Outstanding balance — can be synced automatically |
| EMI | Monthly instalment (₹) |
| Interest rate | Annual rate (%) |
| Tenure | Dropdown: 3 months, 6 months, 9 months, then 1–25 years |
| First EMI date | When your first full EMI was paid — used to count EMIs paid so far |
| Full EMI start date | For home loans: date when construction-period interest-only payments ended |
| Status | Active / Closed / Paused |

#### Loan Analytics panel

Click any loan row to expand a full analytics panel:

| Section | What it shows |
|---|---|
| **EMI Progress** | X of Y EMIs paid, % complete, estimated closure date |
| **Balance Tracker** | Current outstanding balance — edit manually or click **"Sync from schedule"** to auto-recompute from the amortization schedule based on months elapsed since First EMI date |
| **Principal / Interest grid** | 4 tiles: principal paid, interest paid, principal remaining, interest remaining |
| **Total cost of borrowing** | Original principal + total interest = true all-in cost of the loan |
| **EMI bleed meter** | Visual bar showing what fraction of each EMI goes to interest vs principal — the "bleeding money" view |
| **Section 24(b) tracker** | For home loans: interest paid in the current FY (April–March) vs the ₹2 lakh annual deduction limit |
| **Prepayment calculator** | Enter a lump-sum prepayment and see both options side by side: |
| | **Option A — Reduce tenure:** same EMI, months saved, total interest saved, new closure date |
| | **Option B — Reduce EMI:** new lower EMI amount, how much the EMI drops, interest saved, new total interest |
| **Amortization schedule** | Collapsible table showing every EMI: month number, payment, interest component, principal component, balance after. Phase badges distinguish **Pre-EMI** (interest-only) rows from **Full EMI** rows for home loans |

#### Payoff strategies

For all active loans, two priority-sorted lists help you decide where to put extra cash:

- **Avalanche** — highest interest rate first → minimises total interest paid over time
- **Snowball** — smallest balance first → quick psychological wins, motivation-focused

#### Home loans with phased disbursals (on the Asset detail page)

Indian home loans are disbursed in tranches linked to construction milestones. The system handles this correctly:

1. Go to the linked loan's **Asset detail page** → expand the loan → open **Disbursal Schedule**
2. Add each tranche: date, amount (₹), optional notes
3. The amortization engine automatically generates **Pre-EMI** (interest-only) rows for each month from loan start to the full-EMI start date, using the cumulative disbursed amount at that point
4. After the full-EMI start date, the schedule switches to standard reducing-balance on the total disbursed
5. A progress bar shows % of sanctioned amount that has been disbursed so far

---

### Investments (`/investments`)

Track all market-linked and fixed-income holdings.

- **Holdings table** — symbol, quantity, average buy price, current price, current value, absolute gain/loss, % gain/loss; colour-coded green/red
- **Portfolio summary KPIs** — total invested, current value, total P&L, overall return %
- **Fixed income** — FDs, bonds, PPF, NPS with maturity dates, interest rates, and current value
- **SIP step-up projector** — enter monthly SIP, annual step-up %, investment horizon (years), and expected CAGR to see projected corpus at maturity
- **Stocks sub-page** (`/investments/stocks`) — dedicated table for equity and ETF holdings

---

### Assets (`/assets` and `/assets/:id`)

Track physical and illiquid assets — real estate, vehicles, gold.

**Asset types:** Apartment, Plot, Commercial property, Vehicle, Gold, Other

#### Asset list (`/assets`)

- KPI tiles: total assets, current value, purchase price, overall appreciation %
- Add new asset with type, name, purchase date, purchase price, current value

#### Asset detail page (`/assets/:id`)

- **KPI tiles** — total all-in cost, current value, total paid, appreciation %
- **Overview** — edit name, type, purchase date, purchase price, current value, status (Active / Sold)

**Real estate fields:**
- Area (carpet / built-in / super built-in) in sq ft, price per sq ft
- City, developer / builder name
- Possession status: Under Construction / Possessed / N/A
- Possession date, RERA registration number, builder contact

**Vehicle fields:**
- Make, model, year, registration number, fuel type
- Purchase price, current market value, depreciation tracking

**Cost breakdown:**
- Itemised list of every cost component: base price, stamp duty, registration, GST, parking, brokerage, interiors, etc.
- Running total so you always know the true all-in cost

**Payment history:**
- Every payment made against the asset with date and amount
- Useful for tracking construction-linked payments on under-construction flats

**Linked loans:**
- Attach any existing debt record to this asset
- When you select a loan, the sanctioned amount and EMI auto-fill from the debt record
- Full loan analytics panel (EMI progress, balance tracker, prepayment calculator) appears inline
- Disbursal schedule section for home loans (see above)

---

### Net Worth (`/net-worth`)

- **Snapshot history** — line chart and table of total assets vs total liabilities over time
- **Compute from holdings** — one-click snapshot that sums: investments + fixed income + asset values − outstanding debt balances
- Manual snapshot entry for any historical date if you want to back-fill

---

### Goals (`/goals`)

- Create savings targets with a name, target amount, and deadline date
- Progress bars show how close you are to each target
- **Retirement corpus projector** — enter current age, retirement age, expected monthly expenses in retirement, inflation rate, and expected portfolio return to get the corpus you need and the monthly savings required to reach it (persists in `localStorage`)

---

### Income & Tax (`/income`)

- **Income streams** — salary, freelance, rental, dividends, business — with monthly/annual amounts and taxability flag
- **Income summary KPIs** — total monthly income, annual run-rate, number of streams
- **Tax profile inputs** — 80C deductions (ELSS, PPF, LIC, home loan principal), 80D (health insurance premiums) — saved to settings
- **Old vs New regime comparison** — side-by-side estimated tax under both regimes based on your income run-rate and declared deductions, so you can make an informed choice

---

### Reports (`/reports`)

- **FY spending by month** — bar chart showing spend for each month of the current financial year
- **FY summary** — income, expenses, savings rate, and surplus for the year
- **PDF download** — click **Download PDF** or hit `GET /api/reports/fy-summary.pdf` to get a formatted PDF report of the FY summary

---

### Recurring Payments (`/recurring`)

- **Subscriptions** — Netflix, Spotify, gym memberships, SaaS tools — name, amount, billing cycle (monthly/quarterly/annual), next billing date, category
- **Loan EMIs** — read-only view of all active loans and their next EMI dates, pulled from the Debt module

---

### Accounts (`/accounts`)

Manage all your financial accounts in one place.

**Account types:** Savings, Current, Credit Card, Wallet, Investment, Loan, Other

- Add / edit / delete accounts with institution name and masked account number
- Accounts used to tag transactions on import and to filter the Transactions ledger
- The Dashboard "Spend by account" breakdown is driven by these records

---

### Credit Cards (`/credit-cards` and `/credit-cards/:cardId`)

- **Card list** — all cards with credit limit, billing cycle date, due date, outstanding balance
- **Card detail page** — statement list and EMI plan list for a specific card
- **Statement uploads** — attach monthly statements to a card for record-keeping
- **EMI plans** — track purchases converted to EMIs: original amount, tenure, interest rate, start date

---

### Settings (`/settings`)

- **Current financial year** — set the active FY (e.g. `2025-26`); all FY-aware calculations (budgets, tax, reports) use this value
- **Tax deduction inputs** — 80C and 80D amounts that feed the Income & Tax comparison page

---

## Discord Bot

The bot restricts commands to your configured `DISCORD_USER_ID` only (omit it in `.env` for local dev only).

### Logging expenses, transfers, and templates

**Slash:** `/log` with a single natural-language `entry` string.

**Plain text:** Send a message whose **first word** is `log ` (space required), then the same text you would pass to `/log`:

```
/log 450 swiggy using hdfc savings
log transferred 5000 to savings using sbi
log template Netflix 500
```

The parser understands amounts, merchants, categories and payment hints, **account phrases** (`using …`, `from … account`, `via …`), **transfers** (e.g. `10000 from hdfc to icici`, `sent 2000 to icici`), and **templates** (`template <name>` or `t <name>` — see the **Transaction templates** section above). It replies with a confirmation embed.

On the confirmation embed:

- React **❌** to soft-delete (for transfers, **both** legs are removed).
- React **🔄** for a hint to use `/edit` (transfers cannot be edited here; delete and re-log).

### Slash commands

| Command | Description |
|---|---|
| `/log` | Natural-language expense, transfer, or `template` / `t` line (see templates above) |
| `/edit` | Rewrite a Discord-logged **non-transfer** row using `transaction_id` from the embed footer |
| `/undo` | Soft-delete the last Discord-logged row (including both legs of a transfer) |
| `/balance` | Today / this week / this month spend |
| `/budget` | Current FY budget caps |
| `/debt` | Debt summary: outstanding, EMI |
| `/goal` | Savings goals and progress |
| `/net-worth` | Latest net worth snapshot |
| `/report` | FY spend vs income run-rate |
| `/finance_help` | Short command reference |

---

## Bank Statement Import — Supported Formats

| Format | Details |
|---|---|
| **CSV** | UTF-8; auto-detects header row; skips bank name / account number preamble rows and trailing totals/disclaimers |
| **XLSX / XLS** | Same smart header detection; handles merged cells; skips preamble and trailer rows |
| **PDF** | PyMuPDF heuristic line parser; falls back to local LLM (Ollama/LM Studio) if `LOCAL_LLM_URL` is configured; supports password-encrypted PDFs |

**To convert a PDF manually:**

```bash
make pdf-to-csv PDF=~/Downloads/statement.pdf OUT=~/Downloads/out.csv
# Encrypted PDF:
make pdf-to-csv PDF=~/Downloads/statement.pdf OUT=~/Downloads/out.csv PASS=yourpassword
```

---

## Data Conventions

| Convention | Detail |
|---|---|
| Amounts | Always stored in **paise** (integer). ₹1 = 100 paise. The display layer divides by 100. |
| Dates | ISO 8601 strings (`YYYY-MM-DD`). No timezone complexity. |
| Financial year | Stored as `'2025-26'`. FY start = 1 April, FY end = 31 March. |
| Soft deletes | `is_deleted` flag on transactions — records are never hard-deleted from SQLite. |
| Audit log | Every change is logged with old value, new value, and source (`bot` / `dashboard` / `import`). |
| Transaction types | `debit`, `credit`, or `transfer` (internal moves; excluded from spend aggregates). |

---

## Project Structure

```
packages/
  common/src/finance_common/
    db/
      schema.sql              ← Full SQLite schema (transactions, templates, accounts, assets, …)
      migrations.py           ← Runtime ALTER TABLE migrations (idempotent)
    repositories/             ← Async DB layer — one file per domain
    parsing/
      transaction_import.py   ← CSV/XLSX row parsing, header normalisation, 54 merchant rules
      bank_statement_pdf.py   ← PDF parser (heuristic + Ollama/LM Studio fallback)
    types.py                  ← Domain enums: Category, PaymentMode, etc.
    fy.py                     ← Financial year date utilities

  api/src/finance_api/
    main.py                   ← FastAPI app factory + router registration
    routers/                  ← API routers (transactions, accounts, templates, …)
    schemas/                  ← Pydantic v2 request/response models
    services/
      amortization.py         ← Reducing-balance + phased home loan schedules
      transaction_import_service.py  ← Import pipeline orchestrator
      dashboard.py            ← KPI aggregation queries
      net_worth.py            ← Snapshot computation
      pdf_report.py           ← FY summary PDF generation (ReportLab)

  bot/src/finance_bot/
    bot.py                    ← Discord client, message handler, slash commands

dashboard/src/
  pages/                      ← React route components (dashboard, transactions, templates, …)
  components/                 ← Shared UI (KpiCard, Panel, PageHero, etc.)
  lib/
    api.ts                    ← Typed fetch wrappers for every API endpoint
    format.ts                 ← Paise → rupee formatters (compact + full)
  types/api.ts                ← TypeScript types mirroring all API schemas
  constants/                  ← Shared enums (DEBT_TYPES, DEBT_STATUS, etc.)

scripts/
  migrate_from_excel.py       ← One-time import from personal Excel workbook
  seed_demo_data.py           ← Demo data seeder for testing
  bank_statement_pdf_to_csv.py ← Standalone PDF → CSV converter

tests/                        ← pytest suite (asyncio; covers parsers, repos, API)
```

---

## Database Schema (core tables)

| Table | Purpose |
|---|---|
| `transactions` | Ledger rows (`debit` / `credit` / `transfer`); optional `account_id`, `transfer_pair_id`, `tags` |
| `transaction_templates` | Quick-add presets (name, optional amount, category, account, type, notes, tags) |
| `accounts` | Bank accounts, cards, wallets |
| `budgets` | Per-category monthly caps |
| `debts` | Loans with EMI, rate, tenure, first EMI date |
| `loan_disbursals` | Phased disbursal tranches for home loans |
| `investments` | Market holdings (stocks, MF, ETF) |
| `fixed_income` | FDs, bonds, PPF, NPS |
| `goals` | Savings targets |
| `income_sources` | Income streams |
| `net_worth_history` | Point-in-time net worth snapshots |
| `subscriptions` | Recurring payments |
| `credit_cards` | Card metadata |
| `credit_card_statements` | Monthly statements per card |
| `credit_card_emis` | EMI plans on credit cards |
| `merchant_category_map` | Custom merchant → category overrides |
| `audit_log` | Change history for all records |
| `settings` | App-wide config (active FY, tax deduction inputs) |

---

## API Reference

Interactive docs at **http://localhost:8000/docs** (Swagger UI).

### Key endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness check |
| `GET` | `/api/dashboard/summary` | All KPIs for the home dashboard |
| `GET` | `/api/dashboard/alerts` | Budget over-limit and EMI alerts |
| `GET` / `POST` | `/api/transactions/` | List / create a single transaction |
| `POST` | `/api/transactions/transfer` | Create a linked transfer pair (two rows, excluded from spend) |
| `POST` | `/api/transactions/import` | Upload bank statement (multipart/form-data) |
| `POST` | `/api/transactions/bulk-delete` | Soft-delete a list of transaction IDs |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/transaction-templates/` | List / create / update / soft-delete transaction templates |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/debt/` | Loan CRUD |
| `GET` | `/api/debt/summary` | Outstanding total, combined monthly EMI, next EMI hint |
| `GET` | `/api/debt/{id}/amortization` | Full amortization schedule (simple or phased) |
| `POST` | `/api/debt/{id}/sync-balance` | Recompute `current_balance` from schedule using months elapsed |
| `GET` / `POST` / `DELETE` | `/api/debt/{id}/disbursals` | Home loan disbursal tranche CRUD |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/investments/` | Holdings CRUD |
| `GET` | `/api/investments/portfolio-summary` | Aggregate invested / value / P&L |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/fixed-income/` | Fixed income instrument CRUD |
| `GET` | `/api/budget/vs-actual` | Budget caps vs actual spend, current FY |
| `PUT` | `/api/budget/category/{cat}` | Update a category cap |
| `POST` | `/api/budget/rename-category` | Rename a category across all tables |
| `GET` | `/api/reports/fy-spending` | Monthly spend for the active FY |
| `GET` | `/api/reports/fy-summary` | Income, expenses, savings rate for the FY |
| `GET` | `/api/reports/fy-summary.pdf` | Download FY summary as a formatted PDF |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/accounts/` | Account CRUD |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/goals/` | Goal CRUD |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/income/` | Income stream CRUD |
| `GET` | `/api/net-worth/history` | All net worth snapshots |
| `POST` | `/api/net-worth/snapshot` | Create a new snapshot |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/subscriptions/` | Subscription CRUD |
| `GET` / `POST` / `PUT` / `DELETE` | `/api/credit-cards/` | Credit card CRUD |
| `GET` / `PUT` | `/api/settings/` | Read / write app-wide settings |

---

## Development

```bash
# Run tests
make test

# Lint (ruff + mypy strict)
make lint

# Format Python code
make fmt

# Build the dashboard for production
npm run build --prefix dashboard
```

### Adding a schema migration

Edit `packages/common/src/finance_common/db/migrations.py` and add an `ALTER TABLE` (or `CREATE TABLE`) block inside `apply_migrations()`. The function is idempotent — it checks for column / table existence before executing, so it is safe to run on every startup.

### Adding a new API endpoint

1. Create or edit a router in `packages/api/src/finance_api/routers/`
2. Add Pydantic schemas in `packages/api/src/finance_api/schemas/`
3. Register the router in `packages/api/src/finance_api/main.py`
4. Add a typed fetch wrapper in `dashboard/src/lib/api.ts`
5. Update `dashboard/src/types/api.ts` with matching TypeScript types

---

## Disclaimer

Tax estimates, SIP / retirement projections, debt payoff ordering, and regime comparisons are **educational planning aids only** — not financial, legal, or tax advice. Investment quotes depend on third-party data and may be delayed or inaccurate.
