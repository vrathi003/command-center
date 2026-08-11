# Money Engine Changes Brief

**Date:** 2026-08-11  
**Branch tip (at write time):** `main` @ `5bca0a9`  
**Owner:** Vaibhav

Short operator guide for the double-entry money-engine work landed on `main` (P1–P5 + Gmail Intake alignment + CC / Debt / Subscriptions ledger waves W1–W3).

For full design detail see:

| Doc | Path |
|-----|------|
| Parent design | `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md` |
| Alerts (P5) | `docs/superpowers/specs/2026-08-11-double-entry-money-engine-p5-design.md` |
| Gmail ↔ Intake | `docs/superpowers/specs/2026-08-11-gmail-intake-alignment-design.md` |
| CC / Debt / Subs umbrella | `docs/superpowers/specs/2026-08-11-cc-debt-subs-ledger-alignment-design.md` |

---

## 1. What changed (summary)

### Core ledger (P1–P4)

- True double-entry tables: `ledger_transactions` + `ledger_postings` (balanced postings only).
- `LedgerService` is the **only** allowed writer of ledger rows.
- System accounts seeded at migrate/boot: `Opening Balance Equity`, `Uncategorized Expense`, `Uncategorized Income`, `Suspense`.
- Project setting `ledger_engine`: `legacy` | `double_entry` (default **`double_entry`**).
- Legacy history migration API: dry-run + apply → cutover (`legacy_cutover_at` / archive).
- Intake desk for staged candidates; recon scaffolding as dual-books control.
- CI guard: no rogue `INSERT INTO ledger_*` outside `finance_common/ledger/`.

### Alerts (P5)

- Domain jobs emit events; **AlertService** polls / drains and writes `alert_notifications`.
- In-app Alerts API + dashboard `/alerts` banner (ack).
- Budget / EMI / CC due paths no longer depend on Discord for those alerts (Discord stays optional / demoted).

### Gmail ↔ Intake

- Email approve path bridges into Intake (`source=email`, external keys stay `gmail:…` for idempotency).
- Quarantine staging + sync-back; transfer force-as-transfer fixes.
- Email Inbox UI aligned with Intake posting.

### Product surfaces (W1–W3) — package complete

| Wave | Area | Behavior when `ledger_engine=double_entry` |
|------|------|---------------------------------------------|
| **W1** | Credit cards | Pay bill → `build_cc_bill_pay` + `LedgerService.post`. Live outstanding = `max(0, -account_balance_paise(liability_cc))`. Cache `current_balance_paise` refreshed after pay/apply. |
| **W2** | Debt / EMI | Loans get `account_id` (`liability_loan`) + `payment_account_id`. `build_emi_payment`. Manual **Record EMI** + hybrid auto-post when due + both accounts + EMI amount known. |
| **W3** | Subscriptions | Optional `account_id`. Manual **Record charge** → expense via `build_bank_expense` / `build_cc_swipe`. **No silent auto-debit** in v1. |

---

## 2. How to run the stack

```bash
# From repo root — install once
make install

# API + bot
make dev
# or: python start.py

# Dashboard (separate terminal)
make dev-dashboard
```

Defaults: API `http://localhost:8000`, dashboard `http://localhost:3000`.  
DB path from `.env` → `DB_PATH` (example: `~/finance/finance.db`). Schema migrations run on API startup via `finance_common.db.migrations`.

**No separate “run the ledger” daemon.** Ledger writes happen inside the API process when `ledger_engine=double_entry` and ledger health checks pass.

---

## 3. Commands you should know

### Ledger write guard (CI / local)

Bans direct `INSERT` into ledger tables outside the allowed package:

```bash
make check-ledger-writes
# same as:
uv run python scripts/ci_check_ledger_writes.py
```

Wired into `make lint`. Run after any change that touches money writes.

### Tests

```bash
make test
# or focused:
uv run pytest tests/test_debt_emi_ledger.py tests/test_subscription_charge_ledger.py -q --tb=line
uv run pytest tests/ -q --tb=line
```

### Legacy → ledger migration (one-time / ops)

Preview then apply (API must be running, or call via HTTP client):

```http
POST /api/migration/legacy-ledger/dry-run
POST /api/migration/legacy-ledger/apply
```

Apply backs up the SQLite file, migrates eligible legacy `transactions`, and marks cutover. Prefer dry-run first on a copy of production DB.

### Project config (engine switch)

Stored in SQLite `settings` (not `.env`):

| Key idea | Setting |
|----------|---------|
| Engine | `project_config.ledger.engine` → `legacy` \| `double_entry` |
| Cutover timestamp | `project_config.migration.legacy_cutover_at` |

Inspect / update via Settings API (`GET`/`PUT /api/settings/`) which exposes `project_config` including `ledger_engine`.

Default for new installs: **`double_entry`**.

### Other make targets (unchanged)

| Command | Purpose |
|---------|---------|
| `make install` | Python + npm deps |
| `make seed-demo` | Demo data |
| `make migrate` | Excel workbook import (historical; not ledger cutover) |
| `make lint` / `make fmt` | Ruff + mypy (+ ledger write check) |
| `make health` | Service health helper |

---

## 4. Operator checklist (existing DB)

1. Pull `main`, `make install`.
2. Start API once so schema migrations add ledger / alert / debt / subscription columns.
3. Confirm Settings → `ledger_engine` is `double_entry` (or set it).
4. If you still have legacy `transactions` you care about:  
   `POST /api/migration/legacy-ledger/dry-run` → review → `…/apply`.
5. Credit cards: ensure each card has a linked `liability_cc` account for live balance + pay bill.
6. Debts: new/linked loans get a loan account; set **payment account** for auto EMI post; otherwise use **Record EMI** on Debt page.
7. Subscriptions: set payment account; use **Record charge** on Recurring page when billed.
8. After code changes that write money: `make check-ledger-writes` + `make test`.

---

## 5. Dashboard surfaces added / updated

| Page | What to use |
|------|-------------|
| Transactions / Ledger | Manual posts & void via ledger when cut over |
| Intake / Email Inbox | Approve staged email → Intake → ledger |
| Alerts (`/alerts`) | In-app notifications; ack banner |
| Credit Cards | Pay bill (ledger); live outstanding from ledger |
| Debt | **Record EMI** modal |
| Recurring | **Record charge** for subscriptions |

---

## 6. Important invariants

- Amounts stay in **paise** (integers).
- Only `packages/common/src/finance_common/ledger/` may insert `ledger_*` rows.
- When `double_entry`, CC pay / EMI / subscription charge must **not** create legacy `transactions` money rows.
- EMI interest posts to system **Uncategorized Expense** with category `Debt Interest`.
- Subscription charges use sub category or default `Subscriptions`.
- Transfers stay excluded from spend/budget aggregates (same product rule as before).

---

## 7. Deferred (by design)

- Subscription billing-day reminder events (optional later).
- Discord as full Alert delivery channel for every event type.
- Full recon polish / digests beyond what P5 already ships.

---

## 8. Spec / plan index (this wave)

| Plan | Path |
|------|------|
| W1 CC | `docs/superpowers/plans/2026-08-11-credit-cards-ledger-alignment-w1.md` |
| W2 Debt EMI | `docs/superpowers/plans/2026-08-11-debt-emi-ledger-alignment-w2.md` |
| W3 Subscriptions | `docs/superpowers/plans/2026-08-11-subscriptions-ledger-alignment-w3.md` |
| P5 Alerts | `docs/superpowers/plans/2026-08-11-double-entry-money-engine-p5.md` |
| Gmail Intake | `docs/superpowers/plans/2026-08-11-gmail-intake-alignment.md` |
