# Wealth Stack — Ledger Alignment Design

**Date:** 2026-08-11  
**Status:** Approved for phased implementation  
**Owner:** Vaibhav  
**Parent:** `docs/superpowers/specs/2026-08-10-double-entry-money-engine-design.md`  
**Depends on:** P1–P5 + CC/Debt/Subs W1–W3 (money engine live; `ledger_engine=double_entry`)

---

## 1. Goal

Align **Investments**, **Fixed income**, **Net Worth**, **Income & Tax**, and (later) **Goals** with the double-entry money engine so wealth movements post through `LedgerService`, holdings bind to `asset_investment` accounts, Net Worth uses a trustworthy composed lens, and income credits drive savings rate — without treating SIP/buys as budget spend.

---

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Roadmap shape | Full package design; implement **Investments+FI → Net Worth → Income**; Goals deferred |
| Investment accounts | **One `asset_investment` ledger account per holding / FI instrument** (`account_id` on row) |
| Ledger vs market | Ledger = **cost / principal deployed**; MV = `units × current_price` (price sync is **not** a posting) |
| NW valuation | **Composed lens:** ledger BS − inv/FI ledger cost + holdings MV / FI principal overlay (+ other assets module as today) |
| Buy / SIP / FI deposit | **Hybrid:** seed existing rows via Opening Balance Equity; ongoing = manual Record buy/SIP/deposit (no silent auto-SIP) |
| Income | Streams stay **planning**; **Record income** prefilled from stream → `build_bank_income`; savings rate → ledger income credits |
| Goals (this package) | **Progress trackers only** (manual `current_amount`) |
| Goals (later) | Each goal links to an instrument/account; progress from that link |
| DB backfill | Yes — migrations + seed posts for existing holdings/FI (no fake bank debits) |
| Past NW snapshots | Leave history; new snapshots use composed lens after W2 |
| Tax 80C / regime | Remain settings — not ledger posts |

---

## 3. Phased roadmap

| Phase | Name | Deliverable |
|-------|------|-------------|
| **W1** ✅ Done | Investments + Fixed income | `account_id`; seed opening; Record buy/SIP/sell; Record FI deposit/maturity; builders · [acceptance report](../../../.superpowers/sdd/task-7-report.md) |
| **W2** ✅ Done | Net Worth | Composed lens + snapshot job / API / dashboard KPI · [acceptance report](../../../.superpowers/sdd/task-3-report.md) |
| **W3** ✅ Done | Income | Record income from streams; savings rate from ledger credits |
| **W4** (later) | Goals → instruments | Link goal → holding/account; progress from ledger/MV |

Wealth package **W1–W3** is complete for money paths. **Goals W4** is next when scheduled.

---

## 4. Architecture

```
Bank (asset_cash…)          Holding / FI (asset_investment)
        │                              │
        │  buy / SIP / deposit         │
        └──────────► Dr Investment · Cr Bank
                       seed: Dr Investment · Cr Opening Balance Equity
                       sell / maturity: reverse (Cr Investment · Dr Bank)

Net Worth (composed):
  ledger net_worth_totals
  − sum(ledger cost of linked inv/FI accounts)
  + sum(units × current_price) + sum(FI principal)
  + other real assets (assets module)
  − already includes liability_cc / liability_loan when on ledger
```

**Hard rules**
- Only `finance_common/ledger/` inserts `ledger_*`.
- Wealth buys/SIPs/FI deposits are **transfers**, excluded from budget spend.
- When `ledger_engine=double_entry`, wealth money APIs must not insert legacy `transactions`.

---

## 5. Phase W1 — Investments + Fixed income

### 5.1 Schema

- `investments.account_id INTEGER REFERENCES accounts(id)` (nullable until seeded)
- `fixed_income.account_id INTEGER REFERENCES accounts(id)`
- Migration ALTER + `schema.sql`; backfill helper on API startup or dedicated ensure step after migrate

### 5.2 Account bind + seed (existing rows)

For each investment/FI row with `account_id IS NULL` and double_entry:

1. Create `accounts` row: `type` suitable (`investment` / existing type map), `account_class=asset_investment`, name from instrument/institution.
2. Set `account_id` on the holding.
3. **Seed cost** (if cost/principal > 0 and no prior seed external_key):
   - Cost = `round(units * avg_price_paise)` for market holdings; `principal_paise` for FI.
   - Post: `Dr investment_account · Cr Opening Balance Equity` via `LedgerService`  
     `external_key = inv_seed:{investment_id}` / `fi_seed:{fixed_income_id}` (idempotent).
4. Do **not** credit/debit bank on seed.

New holdings created after W1: create account on insert; seed only if user supplies opening cost without a bank leg; otherwise first money move is Record buy/deposit.

### 5.3 Builders

| Action | Builder |
|--------|---------|
| Buy / SIP | existing `build_investment_buy(bank, investment, amount)` |
| Sell / redeem | `build_investment_sell` = inverse (`Dr Bank · Cr Investment`) — add if missing |
| FI deposit | same shape as buy |
| FI maturity / withdrawal to bank | same shape as sell |
| Seed | opening-balance pair vs `Opening Balance Equity` (shared helper with intake pattern) |

### 5.4 APIs

- `POST /investments/{id}/record-buy` — body: `date`, `amount_paise`, `units`, `bank_account_id` (optional avg update)
- `POST /investments/{id}/record-sip` — alias or same as buy with `source=sip` metadata
- `POST /investments/{id}/record-sell` — body: `date`, `amount_paise`, `units`, `bank_account_id`
- `POST /fixed-income/{id}/record-deposit` / `record-maturity`
- All: require double_entry + `account_id`; post ledger; update units/avg/principal on side table; return `ledger_transaction_id`

Holding CRUD remains for metadata (ISIN, sector, prices). **Editing units/avg by hand after bind should be discouraged** when ledger is source of cost — prefer Record buy/sell. Optional: block direct cost edits when `account_id` set, or allow with warning (prefer block cost fields; allow metadata).

### 5.5 Dashboard

Investments / Stocks / FI sections:

- Show linked account / cost from ledger when present
- **Record buy / SIP / sell** modals (bank select, date, units, amount)
- FI: **Record deposit / maturity**
- One-time banner if any holding lacks seed (auto-seed on API boot preferred so user rarely sees this)

### 5.6 Price sync

Unchanged: updates `current_price_paise` only. No MTM journal.

---

## 6. Phase W2 — Net Worth

### 6.1 Composed compute

Replace `compute_totals_from_holdings` (or add parallel path when double_entry):

```
base = await net_worth_totals(conn)  # ledger asset_* − liability_*
inv_cost = sum(account_balance for linked inv accounts)
fi_cost = sum(account_balance for linked FI accounts)
inv_mv, fi_principal = from holdings tables
other_assets = assets module (real estate etc.) if not already on ledger

assets = base.assets - inv_cost - fi_cost + inv_mv + fi_principal + other_assets_not_in_ledger
liabilities = base.liabilities  # CC/loans already ledger when bound
net = assets - liabilities
```

Refine if real-assets already have ledger accounts later; v1 keep assets-module add-on as today.

### 6.2 Snapshots

- Month-end job + manual snapshot API use composed compute
- Historical rows untouched
- Dashboard NW chart/KPI read latest snapshot; optional “live preview” from composed compute

### 6.3 Cash completeness

Ensure active bank/wallet accounts are on ledger (opening seed if needed was legacy migration). Document that unlinked cash still missing from NW until seeded.

---

## 7. Phase W3 — Income

### 7.1 Schema (optional)

- `income_sources.default_account_id` (bank) nullable
- `income_sources.category` nullable (default e.g. `Salary`)

### 7.2 Record income

- `POST /income/{id}/record-income` — body: `date`, `amount_paise?`, `account_id?`, `category?`
- Defaults from stream; `build_bank_income` + Uncategorized Income (or dedicated income account if we add later)
- No auto-post on payday

### 7.3 Savings rate

Dashboard / reports: income leg = **ledger income credits in period**, not `income_sources` monthly equivalent. Streams remain for tax/planning UI and Record income prefills.

---

## 8. Goals — this package vs later

| Now (W1–W3) | Later (W4) |
|-------------|------------|
| CRUD target / current / contribution fields | Optional `investment_id` / `account_id` |
| No ledger posts | Progress = linked holding MV or account balance |
| | Record contribution → buy/transfer into linked instrument |

---

## 9. Acceptance (umbrella)

- W1: existing holdings seeded idempotently; Record buy does not hit budget spend; sell reduces units + investment ledger balance
- W2: NW snapshot matches composed lens; CC/loan liabilities from ledger when bound
- W3: Record income posts; savings rate uses ledger credits
- `make check-ledger-writes` green; no wealth path inserts `ledger_*` outside LedgerService
- Goals unchanged functionally in W1–W3

---

## 10. Out of scope

- Mark-to-market journal entries
- Auto-SIP scheduler
- Full tax engine / slab calculator
- Goal↔instrument linking (W4)
- Rewriting historical `net_worth_history` rows
