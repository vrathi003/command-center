# Subscriptions Ledger Alignment (W3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind subscriptions to a payment `account_id` and post manual **Record charge** expenses through LedgerService (no silent auto-debit).

**Architecture:** Optional `subscriptions.account_id` (payment source). `POST /subscriptions/{id}/record-charge` posts via existing `build_bank_expense` / `build_cc_swipe` + `LedgerService.post`, then advances `next_billing_date` by billing cycle. Recurring page gets Record charge CTA. Reminders stay out of scope for v1.

**Tech Stack:** aiosqlite, FastAPI, pytest, existing ledger builders.

**Spec:** `docs/superpowers/specs/2026-08-11-cc-debt-subs-ledger-alignment-design.md` §6

## Global Constraints

- Amounts in paise integers.
- Only `finance_common/ledger/` inserts `ledger_*`.
- When `ledger_engine=double_entry`, record-charge must not insert legacy `transactions`.
- No auto-debit job in v1 (manual Record charge only).
- `category` column already exists on `subscriptions` — reuse it on postings (default `"Subscriptions"` when null/blank).
- Expense system account: `Uncategorized Expense`.
- TDD; commit per task; do not commit unrelated `uv.lock`.
- Do not re-implement W1/W2.

## File map

| Path | Role |
|------|------|
| `packages/common/src/finance_common/db/schema.sql` | `account_id` on subscriptions |
| `packages/common/src/finance_common/db/migrations.py` | ALTER ADD `account_id` |
| `packages/common/src/finance_common/repositories/subscriptions.py` | row + CRUD fields |
| `packages/api/src/finance_api/schemas/subscription.py` | Out/Create/Put + RecordCharge body/out |
| `packages/api/src/finance_api/routers/subscriptions.py` | CRUD `account_id` + record-charge |
| `packages/api/src/finance_api/services/subscription_charge.py` | post + advance helper (new) |
| `dashboard/src/types/api.ts` | `account_id` on Subscription |
| `dashboard/src/lib/api.ts` | `recordSubscriptionCharge` |
| `dashboard/src/pages/RecurringPaymentsPage.tsx` | Record charge UI |
| `tests/test_subscription_account_schema.py` | schema |
| `tests/test_subscription_charge_ledger.py` | record-charge |

---

### Task 1: Schema — `account_id` on subscriptions

**Files:**
- Modify: `packages/common/src/finance_common/db/schema.sql` (subscriptions table)
- Modify: `packages/common/src/finance_common/db/migrations.py`
- Test: `tests/test_subscription_account_schema.py`

Add nullable `account_id INTEGER REFERENCES accounts(id)` to `subscriptions` (fresh schema + migration ALTER).

- [ ] **Step 1: Write failing test** asserting after `init_db` / migrate, `subscriptions` has `account_id` column (PRAGMA table_info).

- [ ] **Step 2: Run** `uv run pytest tests/test_subscription_account_schema.py -q --tb=short` → FAIL

- [ ] **Step 3: Implement** schema + migration (mirror debts/credit_cards column add pattern).

- [ ] **Step 4: Run test → PASS**

- [ ] **Step 5: Commit** `feat(subscriptions): account_id column`

---

### Task 2: Repository + API schemas expose `account_id`

**Files:**
- Modify: `packages/common/src/finance_common/repositories/subscriptions.py`
- Modify: `packages/api/src/finance_api/schemas/subscription.py`
- Modify: `packages/api/src/finance_api/routers/subscriptions.py`
- Test: extend `tests/test_subscription_account_schema.py` or `tests/test_subscription_charge_ledger.py` create/list round-trip

**Interfaces:**
- Produces: `SubscriptionRow.account_id: int | None`; Create/Put accept optional `account_id`; Out includes `account_id`.

- [ ] **Step 1: Failing test** — create subscription with `account_id`, GET returns it.

- [ ] **Step 2: Implement** SELECT/INSERT/UPDATE columns; schemas; `_to_out` / create / put merge.

- [ ] **Step 3: Tests PASS → commit** `feat(subscriptions): wire account_id through API`

---

### Task 3: `POST /subscriptions/{id}/record-charge`

**Files:**
- Create: `packages/api/src/finance_api/services/subscription_charge.py`
- Modify: `packages/api/src/finance_api/schemas/subscription.py`
- Modify: `packages/api/src/finance_api/routers/subscriptions.py`
- Test: `tests/test_subscription_charge_ledger.py`

**Interfaces:**
```python
async def post_subscription_charge(
    conn: aiosqlite.Connection,
    *,
    sub: SubscriptionRow,
    payment_date: str,  # YYYY-MM-DD
    amount_paise: int | None = None,  # default sub.amount_paise
    account_id: int | None = None,  # override sub.account_id
) -> tuple[int, SubscriptionRow]:
    """Post expense via LedgerService; advance next_billing_date. Returns (ledger_tx_id, updated_sub)."""
```

**Behavior:**
1. Require `ledger_engine=double_entry` (else 422).
2. Resolve payment account = override or `sub.account_id`; if missing → 422.
3. Amount = override or `sub.amount_paise`; must be `> 0`.
4. Category string = `sub.category.strip()` if present else `"Subscriptions"`.
5. Load payment account; if `account_class` / type is credit-card / `liability_cc` → `build_cc_swipe`; else → `build_bank_expense` (asset bank/wallet).
6. Expense account = system `Uncategorized Expense` (same helper pattern as `debt_emi.uncategorized_expense_id`).
7. `LedgerService.post` with merchant=`sub.name`, date=`payment_date`, source=`subscription`.
8. Advance `next_billing_date`: from `payment_date` if current next is null/empty or ≤ payment_date, else from current next — by cycle (`weekly` +7d, `monthly` +1mo via `advance_months`, `quarterly` +3, `yearly` +12). Persist via repo update.
9. Response: `{ "ledger_transaction_id": int, "next_billing_date": str | null, "subscription": SubscriptionOut }`

Body schema:
```python
class RecordChargeBody(BaseModel):
    date: str  # YYYY-MM-DD
    amount_paise: int | None = Field(default=None, gt=0)
    account_id: int | None = Field(default=None, gt=0)
```

- [ ] **Step 1: Failing tests** — bank charge reduces bank balance / increases expense; advances monthly next; CC path uses liability; missing account → 422; no legacy `transactions` row.

- [ ] **Step 2: Implement service + route**

- [ ] **Step 3: PASS → commit** `feat(subscriptions): record-charge ledger post`

---

### Task 4: Dashboard Record charge

**Files:**
- Modify: `dashboard/src/types/api.ts`
- Modify: `dashboard/src/lib/api.ts`
- Modify: `dashboard/src/pages/RecurringPaymentsPage.tsx`

- [ ] Extend Subscription type with `account_id: number | null`
- [ ] Add `recordSubscriptionCharge(id, body)` → POST `/api/subscriptions/{id}/record-charge`
- [ ] On each active subscription row: **Record charge** opens small modal — date (default `next_billing_date` or today), account select (savings/current/wallet/CC; default `account_id`), optional amount override; submit; invalidate subscriptions + ledger queries.
- [ ] Allow saving `account_id` on create/edit if the form already edits fields (minimal: set default payment account in modal and optionally persist via PUT when user checks “remember account”).
- [ ] `npm run build --prefix dashboard` PASS
- [ ] Commit `feat(dashboard): record subscription charge`

---

### Task 5: Acceptance

- [ ] `uv run pytest tests/ -q --tb=line` green
- [ ] `make check-ledger-writes` green
- [ ] Mark W3 ✅ Done on umbrella design; note package complete (W1–W3)
- [ ] Commit `docs(subscriptions): mark ledger W3 complete`

---

## Self-review vs §6

| Spec | Task |
|------|------|
| optional account_id + category | 1–2 (category already present) |
| POST record-charge → LedgerService expense | 3 |
| No auto-debit v1 | 3–5 (no job) |
| Recurring Record charge CTA | 4 |
| Optional billing reminder later | deferred (out of plan) |
