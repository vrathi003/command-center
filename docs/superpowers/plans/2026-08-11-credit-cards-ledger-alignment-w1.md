# Credit Cards Ledger Alignment (W1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route CC bill pay through LedgerService and serve live outstanding from `liability_cc` ledger balances when `double_entry`.

**Architecture:** `pay_bill` uses `build_cc_bill_pay` + `ledger.service.post`. Live balance = `max(0, -account_balance_paise(cc_account_id))`. Statement apply refreshes cached `current_balance_paise` from ledger. Legacy engine path unchanged.

**Tech Stack:** aiosqlite, FastAPI, pytest, existing ledger builders.

**Spec:** `docs/superpowers/specs/2026-08-11-cc-debt-subs-ledger-alignment-design.md` §4

## Global Constraints

- Amounts in paise integers.
- Only `finance_common/ledger/` inserts `ledger_*`.
- When `ledger_engine=double_entry`, pay_bill must not call `insert_transfer_pair`.
- Outstanding display: `max(0, -account_balance_paise(...))` (CC credit-normal).
- TDD; commit per task; do not commit unrelated `uv.lock`.
- Do not implement W2 debt/EMI or W3 subscriptions in this plan.

## File map

| Path | Role |
|------|------|
| `routers/credit_cards.py` | pay_bill + live-balance + apply cache refresh |
| `repositories/credit_cards.py` | optional helper to set current_balance |
| `tests/test_credit_card_pay_bill_ledger.py` | new |
| `tests/test_credit_card_apply_ledger.py` | extend cache refresh if needed |
| Dashboard types/api if response shape changes | optional |

---

### Task 1: pay_bill → LedgerService (double_entry)

**Files:** `packages/api/src/finance_api/routers/credit_cards.py`, `tests/test_credit_card_pay_bill_ledger.py`

- [ ] Write failing test: create bank + CC with linked liability_cc; POST pay-bill; assert ledger postings via `account_balance_paise`; assert no new rows in legacy `transactions` for that payment.
- [ ] Implement double_entry branch: `require_ledger_writes`, `PostTransactionInput` + `build_cc_bill_pay`, `ledger_service.post`, return `{ledger_transaction_id}`.
- [ ] Keep legacy `insert_transfer_pair` when not double_entry.
- [ ] Commit `feat(cc): pay bill through LedgerService`

**Response shape (double_entry):**
```json
{ "ledger_transaction_id": 123 }
```
Legacy keeps `transfer_pair_id` / debit / credit ids.

---

### Task 2: Live balance from ledger

**Files:** `credit_cards.py` router (live-balance + list enrichment if any), tests

- [ ] Helper `_cc_outstanding_paise(conn, account_id) -> int` = `max(0, -await account_balance_paise(conn, account_id))`
- [ ] Use when double_entry + account_id; else `tx_repo.cc_live_balance`
- [ ] Test: after swipe ingest/post + bill pay, live-balance equals expected outstanding
- [ ] Commit `feat(cc): live balance from liability_cc ledger`

---

### Task 3: Refresh cache after statement apply + pay_bill

**Files:** `credit_cards.py` apply + pay_bill

- [ ] After successful double_entry apply and pay_bill, `UPDATE credit_cards SET current_balance_paise = outstanding`
- [ ] Test apply or pay_bill updates cache
- [ ] Commit `feat(cc): sync current_balance_paise from ledger`

---

### Task 4: Acceptance

- [ ] Full pytest + `ci_check_ledger_writes.py`
- [ ] Note under umbrella design or roadmap one-liner W1 done
- [ ] Commit `docs: CC ledger alignment W1 acceptance`

---

## Self-review

| Spec §4 | Task |
|---------|------|
| pay_bill ledger | 1 |
| live balance | 2 |
| cache refresh | 3 |
| tests | 1–4 |
| W2/W3 out | enforced |
