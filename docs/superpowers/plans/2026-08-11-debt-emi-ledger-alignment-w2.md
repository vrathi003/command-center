# Debt + EMI Ledger Alignment (W2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind debts to `liability_loan` accounts and post EMI principal + interest splits through LedgerService (hybrid auto/manual).

**Architecture:** `debts.account_id` → loan liability; `debts.payment_account_id` → bank for EMI. Builder `build_emi_payment`. `POST /debt/{id}/record-emi` posts + advances schedule. Job auto-posts when both accounts + emi amount + due today; else leaves remind path (existing `debt.emi_due` events when P5 present).

**Tech Stack:** aiosqlite, FastAPI, pytest, amortization helpers.

**Spec:** `docs/superpowers/specs/2026-08-11-cc-debt-subs-ledger-alignment-design.md` §5

## Global Constraints

- Amounts in paise; EMI postings must balance.
- Only `finance_common/ledger/` inserts `ledger_*`.
- Interest uses system expense account `Uncategorized Expense` with category `Debt Interest` unless a dedicated expense account exists later.
- Loan outstanding display: `max(0, -account_balance_paise(loan_account_id))` when double_entry.
- Sync `debts.current_balance_paise` from ledger after EMI post.
- TDD; commit per task; no unrelated `uv.lock`.
- Do not implement W3 subscriptions.

## File map

| Path | Role |
|------|------|
| schema.sql + migrations.py | `account_id`, `payment_account_id` on debts |
| repositories/debts.py | fields + CRUD |
| ledger/builders.py | `build_emi_payment` |
| routers/debt.py | create links loan account; record-emi |
| services/debt_emi.py | hybrid auto-post + advance |
| background_jobs.py | call hybrid job |
| DebtPage.tsx | Record EMI UI |
| tests/test_debt_emi_ledger.py | coverage |

---

### Task 1: Schema — debt account links

Add nullable `account_id INTEGER REFERENCES accounts(id)` and `payment_account_id INTEGER REFERENCES accounts(id)` to `debts`. Migration + schema + DebtRow fields.

- [ ] TDD schema → commit `feat(debt): account_id and payment_account_id columns`

---

### Task 2: EMI builder + unit tests

```python
def build_emi_payment(
    *,
    bank_id: int,
    loan_id: int,
    expense_account_id: int,
    principal_paise: int,
    interest_paise: int,
    interest_category: str = "Debt Interest",
) -> tuple[NewPosting, ...]:
    """Dr loan principal + Dr interest expense · Cr bank."""
    total = principal_paise + interest_paise
    return (
        NewPosting(loan_id, principal_paise),
        NewPosting(expense_account_id, interest_paise, interest_category),
        NewPosting(bank_id, -total),
    )
```

Zero-interest: interest_paise=0 still valid (2-posting effectively with 0 interest line — skip zero interest posting if 0 to keep 2-leg).

- [ ] Unit tests balance → commit `feat(ledger): build_emi_payment builder`

---

### Task 3: Ensure loan account on debt create/update + record-emi API

On create (double_entry): create `accounts` type `loan` / `liability_loan` named after debt; set `account_id`. Optional `payment_account_id` on body.

`POST /debt/{id}/record-emi`:
- Body: `date`, optional `principal_paise`/`interest_paise` (default from amortization next row), optional `payment_account_id` override
- double_entry: post EMI via builder + LedgerService; refresh `current_balance_paise` from ledger; advance `next_emi_date` via existing amortization helpers
- Return `{ledger_transaction_id}`

- [ ] API tests → commit `feat(debt): loan accounts and record-emi ledger post`

---

### Task 4: Hybrid auto-post job

Replace pure balance scrub in `auto_advance_debt` when double_entry:
- If `account_id` + `payment_account_id` + `emi_paise` + due date ≤ today → compute principal/interest → post → advance
- Else if due → skip money (remind already via events/Discord); optionally still advance schedule **only if** design says date-only — **prefer: do not reduce balance without post**; only advance date when user records or auto-posts
- Keep legacy path for non-double_entry as today’s balance scrub

- [ ] Job tests → commit `feat(debt): hybrid EMI auto-post job`

---

### Task 5: Dashboard Record EMI

DebtPage: Record EMI button/modal (amount split display, bank select, date) → `recordDebtEmi` API.

- [ ] Build PASS → commit `feat(dashboard): record EMI on debt page`

---

### Task 6: Acceptance

Full pytest + ledger CI; mark W2 done on umbrella design; commit docs.

---

## Self-review vs §5

| Spec | Task |
|------|------|
| liability_loan bind | 1, 3 |
| EMI builder | 2 |
| Hybrid auto/manual | 3–4 |
| Schedule after post | 3–4 |
| UI Record EMI | 5 |
