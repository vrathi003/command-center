# Wealth Investments + Fixed Income Ledger Alignment (W1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind each investment and fixed-income row to an `asset_investment` account, seed existing cost/principal via Opening Balance Equity, and post buy/SIP/sell/deposit/maturity through LedgerService.

**Architecture:** `account_id` on `investments` / `fixed_income`. Idempotent seed posts. Manual Record APIs update units/avg/principal after ledger post. Price sync unchanged. No NW/Income/Goals work in this plan.

**Tech Stack:** aiosqlite, FastAPI, pytest, existing `build_investment_buy`, LedgerService.

**Spec:** `docs/superpowers/specs/2026-08-11-wealth-stack-ledger-alignment-design.md` §5

## Global Constraints

- Amounts in paise integers; units may be float.
- Only `finance_common/ledger/` inserts `ledger_*`.
- Seed uses Opening Balance Equity — never fake bank cash.
- Buy/SIP/deposit must not hit budget spend (transfer shape).
- TDD; commit per task; do not commit unrelated `uv.lock`.
- Do not implement W2 NW, W3 Income, or Goals linking.

## File map

| Path | Role |
|------|------|
| `schema.sql` + `migrations.py` | `account_id` on investments + fixed_income |
| `repositories/investments.py`, `fixed_income.py` | fields + CRUD |
| `ledger/builders.py` | `build_investment_sell` (+ reuse buy for deposit) |
| `services/investment_ledger.py` (new) | ensure account, seed, record buy/sell |
| `services/fixed_income_ledger.py` (new) or shared | FI seed + deposit/maturity |
| `routers/investment.py`, `fixed_income.py` | ensure on create; record-* endpoints |
| Dashboard Investments pages | Record buy/SIP/sell/deposit UI |
| `tests/test_investment_ledger_w1.py` | coverage |

---

### Task 1: Schema — `account_id` on investments + fixed_income

**Files:** schema.sql, migrations.py, tests/test_investment_account_schema.py

- [ ] Failing test: after ensure_database, both tables have `account_id`
- [ ] Migration ALTER + schema columns
- [ ] Commit `feat(wealth): account_id on investments and fixed_income`

---

### Task 2: `build_investment_sell` + unit tests

```python
def build_investment_sell(
    *,
    bank_id: int,
    investment_account_id: int,
    amount_paise: int,
) -> tuple[NewPosting, ...]:
    """Debit bank, credit investment asset (reduce holding cost)."""
    return (
        NewPosting(bank_id, amount_paise),
        NewPosting(investment_account_id, -amount_paise),
    )
```

- [ ] Balance tests; commit `feat(ledger): build_investment_sell builder`

---

### Task 3: Ensure account + idempotent seed

**Files:** `packages/api/src/finance_api/services/investment_ledger.py` (and FI helper)

```python
async def ensure_investment_account_and_seed(conn, inv_row) -> int:
    """Create asset_investment account if needed; seed cost vs Opening Balance Equity once."""

async def ensure_fixed_income_account_and_seed(conn, fi_row) -> int: ...
```

- Seed amount: `int(round(units * avg_price_paise))` if both set else 0; FI = `principal_paise`
- `external_key`: `inv_seed:{id}` / `fi_seed:{id}`
- Skip seed if amount ≤ 0 or external_key already posted
- Call from list/get or explicit `POST /investments/ensure-ledger` + on create; also invoke once from API lifespan or first wealth read when double_entry

- [ ] Tests: seed creates balanced postings; second call no-op; no bank balance change
- [ ] Commit `feat(wealth): seed investment and FI ledger accounts`

---

### Task 4: Record buy / SIP / sell APIs

**Files:** investment router + schemas + investment_ledger service

- `POST /investments/{id}/record-buy` (SIP can share body with `kind: buy|sip` note in merchant/narration)
- `POST /investments/{id}/record-sell`
- Body: `date`, `amount_paise` (>0), `units` (>0), `bank_account_id`
- double_entry only; ensure account; post; update units/avg_price on buy; decrease units on sell (avg unchanged or weighted — use standard weighted avg on buy; on sell reduce units only)
- Return `{ledger_transaction_id, investment: ...}`

- [ ] API tests; commit `feat(investments): record buy/sell through ledger`

---

### Task 5: Record FI deposit / maturity APIs

- `POST /fixed-income/{id}/record-deposit` — increases principal + buy-shaped post
- `POST /fixed-income/{id}/record-maturity` — principal → 0 or reduce + sell-shaped post to bank
- [ ] Tests; commit `feat(fixed-income): record deposit/maturity through ledger`

---

### Task 6: Dashboard Record flows

- Types + `recordInvestmentBuy` / `Sell` / FI helpers in `api.ts`
- InvestmentsPage (and FI section): buttons + modals
- [ ] `npm run build --prefix dashboard` PASS
- [ ] Commit `feat(dashboard): record investment buy/sell and FI moves`

---

### Task 7: Acceptance

- Full pytest + `make check-ledger-writes`
- Mark W1 ✅ on umbrella wealth design
- Commit `docs(wealth): mark investments ledger W1 complete`

---

## Self-review vs §5

| Spec | Task |
|------|------|
| account_id schema | 1 |
| sell builder | 2 |
| seed existing | 3 |
| buy/SIP/sell API | 4 |
| FI deposit/maturity | 5 |
| Dashboard | 6 |
| Acceptance | 7 |
