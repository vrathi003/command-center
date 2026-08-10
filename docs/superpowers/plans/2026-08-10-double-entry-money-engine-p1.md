# Double-Entry Money Engine P1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a double-entry ledger engine (schema + `LedgerService` + balance/report lenses + `project_config` + Discord writers off) that can post balanced transactions and expose named KPIs, while leaving legacy `transactions` intact until P3 migration.

**Architecture:** New tables `ledger_transactions` / `ledger_postings` sit beside legacy `transactions`. All new writes go through `finance_common.ledger.LedgerService`. Read lenses (`BalanceService`, `ReportsService`) query postings only. Product flags live in SQLite `settings` under `project_config.*`. Discord bot process is gated by `project_config.discord.enabled` (default `false`).

**Tech Stack:** Python 3.14+, aiosqlite, FastAPI, Pydantic v2, pytest-asyncio / Starlette TestClient, uv workspace (`finance-common`, `finance-api`, `finance-bot`), existing `settings` KV table.

**Spec:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md` (P1 section §14).

## Global Constraints

- Amounts are integer **paise** only (`Paise`); never float in persistence.
- Signed posting amounts: **positive = debit**, **negative = credit**; posted tx must sum to `0`.
- No adapter may `INSERT INTO ledger_transactions` / `ledger_postings` outside `finance_common/ledger/`.
- Domain code must not import `finance_api.services.discord_notify` or Discord SDK.
- Do not migrate legacy rows in P1 (P3). Do not build Intake/Alert/Recon in P1.
- TDD: failing test → implement → pass → commit per task.
- Use `uv run pytest …` from repo root; activate project venv via uv.

## Phase roadmap (separate plans)

| Phase | Plan file | Status |
|-------|-----------|--------|
| P1 Ledger + lenses + config + Discord off | **this file** | ready |
| P2 Intake + quarantine + dedupe | `docs/superpowers/plans/2026-08-10-double-entry-money-engine-p2.md` | write after P1 |
| P3 Migration + quarantine desk + cutover | `…-p3.md` | after P2 |
| P4 Reconciliation | `…-p4.md` | after P3 |
| P5 AlertService (in-app) | `…-p5.md` | can parallel after P1 events stub |
| P6 Wealth polish | `…-p6.md` | after P3 |

---

## File map (P1)

| Path | Responsibility |
|------|----------------|
| `packages/common/src/finance_common/types.py` | Add `AccountClass` StrEnum |
| `packages/common/src/finance_common/db/schema.sql` | DDL for ledger tables + `accounts.account_class` |
| `packages/common/src/finance_common/db/migrations.py` | Idempotent migrate for existing DBs + system accounts seed |
| `packages/common/src/finance_common/project_config.py` | **Create** — load/save typed project config from `settings` |
| `packages/common/src/finance_common/ledger/__init__.py` | **Create** — public exports |
| `packages/common/src/finance_common/ledger/models.py` | **Create** — dataclasses for NewPosting, PostedTransaction |
| `packages/common/src/finance_common/ledger/errors.py` | **Create** — `LedgerError`, `UnbalancedTransactionError`, … |
| `packages/common/src/finance_common/ledger/service.py` | **Create** — `LedgerService.post` / `void` / `get` |
| `packages/common/src/finance_common/ledger/builders.py` | **Create** — helpers: expense, income, transfer, cc_swipe, cc_bill_pay, investment_buy |
| `packages/common/src/finance_common/ledger/balances.py` | **Create** — `account_balance_paise`, `net_worth_totals` |
| `packages/common/src/finance_common/ledger/reports.py` | **Create** — `budget_spend`, `cash_flow` lenses |
| `packages/common/src/finance_common/ledger/integrity.py` | **Create** — `assert_posted_balanced` for boot |
| `packages/common/src/finance_common/repositories/accounts.py` | Support `account_class` on create/list |
| `packages/api/src/finance_api/schemas/ledger.py` | **Create** — API models |
| `packages/api/src/finance_api/routers/ledger.py` | **Create** — post/void/get + balances + lens KPIs |
| `packages/api/src/finance_api/main.py` | Register ledger router; boot integrity when engine=double_entry |
| `packages/api/src/finance_api/routers/settings.py` | Expose/patch `project_config` subset |
| `start.py` | Gate Discord spawn on `project_config.discord.enabled` |
| `packages/bot/src/finance_bot/main.py` | Exit early if discord disabled in DB config (defense in depth) |
| `tests/test_ledger_service.py` | **Create** |
| `tests/test_ledger_lenses.py` | **Create** |
| `tests/test_project_config.py` | **Create** |
| `tests/test_ledger_api.py` | **Create** |
| `scripts/ci_check_ledger_writes.py` | **Create** — grep ban on rogue INSERTs |
| `Makefile` | Optional target `make check-ledger-writes` |

---

### Task 1: `AccountClass` enum + failing migration test

**Files:**
- Modify: `packages/common/src/finance_common/types.py`
- Create: `tests/test_ledger_schema.py`
- Modify: `packages/common/src/finance_common/db/schema.sql`
- Modify: `packages/common/src/finance_common/db/migrations.py`

**Interfaces:**
- Produces: `AccountClass` StrEnum with values  
  `asset_cash`, `asset_investment`, `asset_other`, `liability_cc`, `liability_loan`, `equity`, `income`, `expense`

- [ ] **Step 1: Write failing test for ledger tables + account_class**

```python
# tests/test_ledger_schema.py
from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import pytest

from finance_common.db import ensure_database
from finance_common.types import AccountClass


@pytest.mark.asyncio
async def test_ledger_tables_exist_after_ensure(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cur = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('ledger_transactions', 'ledger_postings')"
        )
        names = {r[0] for r in await cur.fetchall()}
        assert names == {"ledger_transactions", "ledger_postings"}
        cur = await conn.execute("PRAGMA table_info(accounts)")
        cols = {r[1] for r in await cur.fetchall()}
        assert "account_class" in cols
        cur = await conn.execute(
            "SELECT name FROM accounts WHERE account_class = ?",
            (AccountClass.EQUITY.value,),
        )
        equity_names = {r[0] for r in await cur.fetchall()}
        assert "Opening Balance Equity" in equity_names
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/test_ledger_schema.py::test_ledger_tables_exist_after_ensure -v`  
Expected: FAIL (tables missing / AccountClass missing)

- [ ] **Step 3: Add `AccountClass` to `types.py`**

```python
class AccountClass(StrEnum):
    ASSET_CASH = "asset_cash"
    ASSET_INVESTMENT = "asset_investment"
    ASSET_OTHER = "asset_other"
    LIABILITY_CC = "liability_cc"
    LIABILITY_LOAN = "liability_loan"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"
```

- [ ] **Step 4: Append DDL to `schema.sql`**

After `accounts` table definition, ensure column exists on fresh installs by replacing/extending `CREATE TABLE accounts` to include:

```sql
    account_class TEXT NOT NULL DEFAULT 'asset_cash',
```

Append (end of file):

```sql
CREATE TABLE IF NOT EXISTS ledger_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    payee TEXT,
    notes TEXT,
    tags TEXT,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'posted'
        CHECK (status IN ('posted', 'void')),
    external_key TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_tx_external_key
    ON ledger_transactions(external_key)
    WHERE external_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ledger_tx_date ON ledger_transactions(date);
CREATE INDEX IF NOT EXISTS idx_ledger_tx_status ON ledger_transactions(status);

CREATE TABLE IF NOT EXISTS ledger_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER NOT NULL REFERENCES ledger_transactions(id),
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    amount_paise INTEGER NOT NULL CHECK (amount_paise != 0),
    category TEXT,
    reconciled_statement_line_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ledger_postings_tx ON ledger_postings(transaction_id);
CREATE INDEX IF NOT EXISTS idx_ledger_postings_account ON ledger_postings(account_id);
CREATE INDEX IF NOT EXISTS idx_ledger_postings_category ON ledger_postings(category);
```

- [ ] **Step 5: Add migration + system account seed in `migrations.py`**

At end of `apply_migrations`:

1. `ALTER TABLE accounts ADD COLUMN account_class TEXT NOT NULL DEFAULT 'asset_cash'` if missing  
2. Create `ledger_transactions` / `ledger_postings` if missing (same DDL)  
3. Seed system accounts if not present by name:

```python
_SYSTEM_ACCOUNTS = [
    ("Opening Balance Equity", "equity", AccountClass.EQUITY.value),
    ("Uncategorized Expense", "expense", AccountClass.EXPENSE.value),
    ("Uncategorized Income", "income", AccountClass.INCOME.value),
    ("Suspense", "other", AccountClass.EQUITY.value),
]
```

Use `INSERT OR IGNORE` keyed by unique name — if `accounts.name` is not UNIQUE, select-by-name then insert.

Also map existing `accounts.type` loosely:
- `credit_card` → `liability_cc`
- `loan` → `liability_loan`
- `investment` → `asset_investment`
- else → `asset_cash`  
(only where `account_class` still default and type matches)

- [ ] **Step 6: Run test — expect PASS**

Run: `uv run pytest tests/test_ledger_schema.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add packages/common/src/finance_common/types.py \
  packages/common/src/finance_common/db/schema.sql \
  packages/common/src/finance_common/db/migrations.py \
  tests/test_ledger_schema.py
git commit -m "feat(ledger): schema for double-entry postings and account_class"
```

---

### Task 2: `project_config` load/save

**Files:**
- Create: `packages/common/src/finance_common/project_config.py`
- Create: `tests/test_project_config.py`
- Modify: `packages/common/src/finance_common/repositories/settings_repo.py` (defaults)

**Interfaces:**
- Produces:
  - `@dataclass ProjectConfig` with fields:  
    `discord_enabled: bool = False`,  
    `discord_alerts_enabled: bool = False`,  
    `alerts_in_app_enabled: bool = True`,  
    `ledger_engine: Literal["legacy", "double_entry"] = "double_entry"`,  
    `intake_auto_post_min_confidence: float = 0.85`,  
    `intake_duplicate_date_window_days: int = 1`
  - `async def load_project_config(conn) -> ProjectConfig`
  - `async def save_project_config(conn, cfg: ProjectConfig) -> None`
- Settings keys: `project_config.discord.enabled`, `project_config.discord.alerts.enabled`, `project_config.alerts.in_app.enabled`, `project_config.ledger.engine`, `project_config.intake.auto_post.min_confidence`, `project_config.intake.duplicate.date_window_days`

- [ ] **Step 1: Failing tests**

```python
# tests/test_project_config.py
import pytest
from pathlib import Path
import aiosqlite
from finance_common.db import ensure_database
from finance_common.project_config import load_project_config, save_project_config, ProjectConfig

@pytest.mark.asyncio
async def test_defaults_discord_off(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        cfg = await load_project_config(conn)
    assert cfg.discord_enabled is False
    assert cfg.ledger_engine == "double_entry"

@pytest.mark.asyncio
async def test_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await save_project_config(
            conn,
            ProjectConfig(discord_enabled=True, ledger_engine="legacy"),
        )
        cfg = await load_project_config(conn)
    assert cfg.discord_enabled is True
    assert cfg.ledger_engine == "legacy"
```

- [ ] **Step 2: Run — expect FAIL** (`project_config` missing)

Run: `uv run pytest tests/test_project_config.py -v`

- [ ] **Step 3: Implement `project_config.py`**

Use `settings_repo.get_value` / `set_value`. Parse bools as `"true"`/`"false"`. On missing keys, return dataclass defaults. `save_project_config` writes all keys. Call `await conn.commit()` after sets if `set_value` does not.

Seed defaults in `ensure_defaults` via `INSERT OR IGNORE` for each key with default string values.

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add packages/common/src/finance_common/project_config.py \
  packages/common/src/finance_common/repositories/settings_repo.py \
  tests/test_project_config.py
git commit -m "feat: project_config with Discord off and double_entry default"
```

---

### Task 3: `LedgerService.post` — reject unbalanced

**Files:**
- Create: `packages/common/src/finance_common/ledger/errors.py`
- Create: `packages/common/src/finance_common/ledger/models.py`
- Create: `packages/common/src/finance_common/ledger/service.py`
- Create: `packages/common/src/finance_common/ledger/__init__.py`
- Create: `tests/test_ledger_service.py`

**Interfaces:**
- Produces:
```python
@dataclass(frozen=True, slots=True)
class NewPosting:
    account_id: int
    amount_paise: int  # signed
    category: str | None = None

@dataclass(frozen=True, slots=True)
class PostTransactionInput:
    tx_date: date
    postings: tuple[NewPosting, ...]
    payee: str | None = None
    notes: str | None = None
    tags: str | None = None
    source: str = "manual"
    external_key: str | None = None

async def post(conn, inp: PostTransactionInput) -> int  # transaction id
async def void(conn, transaction_id: int) -> None
async def get_transaction(conn, transaction_id: int) -> PostedTransaction
```

- [ ] **Step 1: Failing tests**

```python
# tests/test_ledger_service.py
@pytest.mark.asyncio
async def test_reject_unbalanced(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT INTO accounts (name, type, account_class) VALUES ('A','savings','asset_cash')"
        )
        await conn.execute(
            "INSERT INTO accounts (name, type, account_class) VALUES ('E','expense','expense')"
        )
        await conn.commit()
        # ids  — query them
        cur = await conn.execute("SELECT id, name FROM accounts WHERE name IN ('A','E')")
        ids = {n: i for i, n in await cur.fetchall()}
        with pytest.raises(UnbalancedTransactionError):
            await ledger_service.post(
                conn,
                PostTransactionInput(
                    tx_date=date(2026, 8, 1),
                    postings=(
                        NewPosting(ids["E"], 10000, "Food Delivery"),
                        NewPosting(ids["A"], -9000),  # not balanced
                    ),
                    source="manual",
                ),
            )

@pytest.mark.asyncio
async def test_post_balanced_expense(tmp_path: Path) -> None:
    db = tmp_path / "l.db"
    await ensure_database(db)
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "INSERT INTO accounts (name, type, account_class) VALUES ('A','savings','asset_cash')"
        )
        await conn.execute(
            "INSERT INTO accounts (name, type, account_class) VALUES ('E','expense','expense')"
        )
        await conn.commit()
        cur = await conn.execute("SELECT id, name FROM accounts WHERE name IN ('A','E')")
        ids = {n: i for i, n in await cur.fetchall()}
        tx_id = await ledger_service.post(
            conn,
            PostTransactionInput(
                tx_date=date(2026, 8, 1),
                postings=(
                    NewPosting(ids["E"], 50000, "Food Delivery"),
                    NewPosting(ids["A"], -50000),
                ),
                source="manual",
                payee="Swiggy",
            ),
        )
        posted = await ledger_service.get_transaction(conn, tx_id)
        assert posted.status == "posted"
        assert sum(p.amount_paise for p in posted.postings) == 0
```

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement `post`**

Algorithm:
1. If `len(postings) < 2` → `LedgerError`
2. If `sum(p.amount_paise) != 0` → `UnbalancedTransactionError`
3. If any `amount_paise == 0` → `LedgerError`
4. Verify each `account_id` exists
5. `BEGIN IMMEDIATE`; insert header; insert postings; `COMMIT`
6. On `external_key` unique conflict → return existing id (idempotent) or raise `DuplicateExternalKeyError` that callers treat as success-get — **prefer: SELECT by external_key first; if posted exists, return its id without inserting**

- [ ] **Step 4: Implement `void`**

Set `status='void'` on header only (postings remain for audit; **balances and lenses must ignore void**). Reject double-void.

- [ ] **Step 5: Tests PASS + commit**

```bash
git add packages/common/src/finance_common/ledger tests/test_ledger_service.py
git commit -m "feat(ledger): LedgerService post/void with balance invariants"
```

---

### Task 4: Posting builders

**Files:**
- Create: `packages/common/src/finance_common/ledger/builders.py`
- Modify: `tests/test_ledger_service.py` (add builder tests)

**Interfaces:**
```python
def build_bank_expense(*, bank_id, expense_account_id, amount_paise: int, category: str) -> tuple[NewPosting, ...]
def build_bank_income(*, bank_id, income_account_id, amount_paise: int, category: str) -> tuple[NewPosting, ...]
def build_transfer(*, from_account_id, to_account_id, amount_paise: int) -> tuple[NewPosting, ...]
def build_cc_swipe(*, cc_id, expense_account_id, amount_paise: int, category: str) -> tuple[NewPosting, ...]
def build_cc_bill_pay(*, bank_id, cc_id, amount_paise: int) -> tuple[NewPosting, ...]
def build_investment_buy(*, bank_id, investment_account_id, amount_paise: int) -> tuple[NewPosting, ...]
```

All `amount_paise` args are **positive magnitudes**; builders apply signs.

- [ ] **Step 1: Failing tests** — cc swipe increases liability (credit on CC = negative posting on liability account… wait: liability normal credit means **negative** amount in our sign convention increases what we owe?  

**Sign convention lock (document in `builders.py` docstring):**
- Asset increase = debit = `+amount`
- Asset decrease = credit = `-amount`
- Liability increase = credit = `-amount`
- Liability decrease = debit = `+amount`
- Expense increase = debit = `+amount`
- Income increase = credit = `-amount`

CC swipe ₹100: Expense `+10000`, CC `-10000`.  
Bill pay ₹100: CC `+10000`, Bank `-10000`.

- [ ] **Step 2: Implement builders + post via LedgerService in tests; assert balances in Task 5**

For Task 4, assert posting tuples only.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(ledger): posting builders for expense, CC, transfer, SIP"
```

---

### Task 5: `BalanceService` + NW totals

**Files:**
- Create: `packages/common/src/finance_common/ledger/balances.py`
- Create: `tests/test_ledger_balances.py`

**Interfaces:**
```python
async def account_balance_paise(conn, account_id: int) -> int
async def balances_for_accounts(conn, account_ids: list[int]) -> dict[int, int]
async def net_worth_totals(conn) -> tuple[int, int, int]  # assets, liabilities, net
```

**Balance formula:**  
`SUM(amount_paise)` over postings joined to `ledger_transactions` where `status='posted'`.

**Display owed on liability:** `max(0, -balance)` when presenting “outstanding”, but `account_balance_paise` returns raw sum.  
`net_worth_totals`: sum raw balances for `asset_*` as assets; for `liability_*` add `-balance` (since credits are negative, owed is positive contribution to liabilities).

```python
# liability contribution to NW liabilities side:
# raw balance for CC after swipe 100 = -10000 → liability_total += 10000
liability_total = sum(-bal for each liability account bal)
asset_total = sum(bal for each asset account bal)
```

- [ ] **Step 1: Fixture posts** — bank expense, cc swipe, bill pay, investment buy; assert raw balances and NW

- [ ] **Step 2: Implement**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(ledger): account balances and net worth from postings"
```

---

### Task 6: Report lenses (budget spend + cash flow)

**Files:**
- Create: `packages/common/src/finance_common/ledger/reports.py`
- Create: `tests/test_ledger_lenses.py`

**Interfaces:**
```python
async def budget_spend_by_category(
    conn, *, start: date, end: date
) -> dict[str, int]:
    """Sum of debit postings (amount_paise > 0) to expense-class accounts in range."""

async def budget_spend_total(conn, *, start: date, end: date) -> int: ...

async def cash_flow_for_accounts(
    conn, *, account_ids: list[int], start: date, end: date
) -> tuple[int, int]:
    """Returns (cash_in_paise, cash_out_paise) from postings on those cash accounts.
    cash_in = sum of positive postings; cash_out = -sum of negative postings.
    """
```

**Golden fixture (lock in test):**

1. CC swipe Food ₹500 → budget Food=50000; cash out=0  
2. Bank UPI Food ₹200 → budget Food+=20000; cash out=20000  
3. Salary ₹100000 to bank → budget unchanged; cash in=10000000  
4. CC bill pay ₹500 → budget unchanged; cash out+=50000; CC liability ↓  
5. SIP ₹1000 bank→investment → budget unchanged; cash out+=100000  

- [ ] **Step 1: Write golden test exactly as above**

- [ ] **Step 2: Run FAIL → implement → PASS**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(ledger): budget spend and cash-flow lenses with golden tests"
```

---

### Task 7: Boot integrity guard

**Files:**
- Create: `packages/common/src/finance_common/ledger/integrity.py`
- Modify: `packages/api/src/finance_api/main.py`
- Create: `tests/test_ledger_integrity.py`

**Interfaces:**
```python
async def find_unbalanced_posted_transaction_ids(conn) -> list[int]:
async def assert_ledger_healthy(conn) -> None:  # raises LedgerIntegrityError
```

- [ ] **Step 1: Test** — manually insert unbalanced header+postings with raw SQL in test; `assert_ledger_healthy` raises

- [ ] **Step 2: On API lifespan startup**, if `load_project_config().ledger_engine == "double_entry"`, run `assert_ledger_healthy`. On failure: log error and set app state `ledger_writes_enabled=False`. Ledger write routes return 503.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(ledger): boot integrity check gates write routes"
```

---

### Task 8: Ledger HTTP API

**Files:**
- Create: `packages/api/src/finance_api/schemas/ledger.py`
- Create: `packages/api/src/finance_api/routers/ledger.py`
- Modify: `packages/api/src/finance_api/main.py`
- Create: `tests/test_ledger_api.py`

**Endpoints:**
- `POST /api/ledger/transactions` — body: date, payee, notes, source, external_key?, postings[{account_id, amount_paise, category?}] OR `pattern` enum + fields for builders
- `POST /api/ledger/transactions/{id}/void`
- `GET /api/ledger/transactions/{id}`
- `GET /api/ledger/accounts/{account_id}/balance`
- `GET /api/ledger/summary/month?year=&month=` →  
  `{ budget_spend_month_paise, cash_out_month_paise, cash_in_month_paise, net_worth_paise, budget_spend_by_category }`

Prefer **pattern helpers** on create for UI safety:

```json
{
  "date": "2026-08-01",
  "pattern": "bank_expense",
  "amount_paise": 50000,
  "bank_account_id": 1,
  "expense_account_id": 2,
  "category": "Food Delivery",
  "payee": "Swiggy"
}
```

Supported patterns: `bank_expense`, `bank_income`, `transfer`, `cc_swipe`, `cc_bill_pay`, `investment_buy`, `custom` (raw postings).

- [ ] **Step 1: API tests with TestClient** (create accounts via `/api/accounts/` or direct seed in fixture)

- [ ] **Step 2: Implement router + register**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): ledger post/void/balance/summary endpoints"
```

---

### Task 9: Settings API for project_config + Discord spawn gate

**Files:**
- Modify: `packages/api/src/finance_api/schemas/app_settings.py`
- Modify: `packages/api/src/finance_api/routers/settings.py`
- Modify: `start.py`
- Modify: `packages/bot/src/finance_bot/main.py`
- Modify: `tests/test_api.py` or create `tests/test_settings_project_config.py`

**Behavior:**
- `GET /api/settings/` includes `project_config` object (discord_enabled, ledger_engine, …)
- `PUT /api/settings/` accepts optional `project_config` patch
- `start.py`: spawn bot only if env token present **AND** `discord_enabled` is true  
  (read DB via small sync/async bootstrap: `ensure_database` + `load_project_config`; default false → **never spawn** unless user enables)
- `finance_bot.main`: after loading settings, open DB and exit 0 with log if `discord_enabled` is false

- [ ] **Step 1: Test GET defaults show discord_enabled false**

- [ ] **Step 2: Implement**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: project_config in settings API; Discord off by default"
```

---

### Task 10: CI guard — no rogue ledger INSERTs

**Files:**
- Create: `scripts/ci_check_ledger_writes.py`
- Modify: `Makefile` (add `check-ledger-writes` and wire into `lint` if present)

**Script logic:**  
`rg -n "INSERT INTO ledger_(transactions|postings)" --glob '!**/ledger/**' --glob '!**/migrations.py' --glob '!**/schema.sql' --glob '!tests/**'`  
Exit 1 if matches outside allowlist.

Allowlist paths:
- `packages/common/src/finance_common/ledger/`
- `packages/common/src/finance_common/db/migrations.py`
- `packages/common/src/finance_common/db/schema.sql`

- [ ] **Step 1: Run script on clean tree — exit 0**

- [ ] **Step 2: Commit**

```bash
git commit -m "ci: ban ledger INSERTs outside LedgerService package"
```

---

### Task 11: Accounts API knows `account_class`

**Files:**
- Modify: `packages/common/src/finance_common/repositories/accounts.py`
- Modify: `packages/api/src/finance_api/schemas/` (accounts schemas)
- Modify: `packages/api/src/finance_api/routers/accounts.py`
- Modify: `dashboard/src/types/api.ts` (add optional `account_class`)
- Test: extend accounts tests or `tests/test_ledger_api.py`

- [ ] **Step 1:** Creating account accepts `account_class`; defaults from `type` mapping  
- [ ] **Step 2:** List/get return `account_class`  
- [ ] **Step 3:** Commit  

```bash
git commit -m "feat(accounts): persist and expose account_class for ledger"
```

---

### Task 12: P1 acceptance checklist (manual + automated)

- [ ] **Step 1: Run full ledger test suite**

```bash
uv run pytest tests/test_ledger_schema.py tests/test_project_config.py \
  tests/test_ledger_service.py tests/test_ledger_balances.py \
  tests/test_ledger_lenses.py tests/test_ledger_integrity.py \
  tests/test_ledger_api.py tests/test_settings_project_config.py -v
```

Expected: all PASS

- [ ] **Step 2: Run CI write guard**

```bash
uv run python scripts/ci_check_ledger_writes.py
```

Expected: exit 0

- [ ] **Step 3: Manual smoke**

1. `make dev` / `python start.py` — API up, **Discord bot not started**  
2. Create cash + expense + CC accounts with correct `account_class`  
3. `POST` cc_swipe + bank_expense + cc_bill_pay + investment_buy  
4. `GET /api/ledger/summary/month` — budget spend excludes bill pay and SIP; cash out includes them  
5. Confirm legacy `/api/transactions/` still works (untouched)

- [ ] **Step 4: Final P1 commit if any docs tweaks**

```bash
git commit -m "docs: note P1 ledger engine available alongside legacy transactions"
```

---

## Spec coverage (P1 only)

| Spec requirement | Task |
|------------------|------|
| Double-entry tables + signed postings | 1, 3 |
| Account classes + system accounts | 1, 11 |
| LedgerService only writer + invariants | 3, 10 |
| Builders (swipe, bill pay, SIP, transfer) | 4 |
| Balance one formula / NW from assets+liabilities | 5 |
| Budget vs cash-flow lenses + golden tests | 6 |
| Boot fail-closed writes | 7 |
| Named summary KPIs | 8 |
| project_config Discord off | 2, 9 |
| No Intake/Alert/Recon/Migration | deferred P2–P5 |

## Out of scope reminders

- Do not change import/email to use LedgerService yet (P2)  
- Do not delete/rename legacy `transactions` (P3)  
- Do not implement AlertService (P5) — no Discord notify refactors required beyond not spawning bot  
- Dashboard full UI rewrite can wait; P1 API is enough for verification  

---

## Self-review notes

- No TBD placeholders in task steps  
- Sign convention documented in Task 4 (liability increase = negative posting)  
- Types consistent: `NewPosting`, `PostTransactionInput`, `AccountClass`, `ProjectConfig`  
- P2–P6 intentionally separate plans so each ships testable software  
