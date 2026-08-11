# Task 3 — Loan accounts + record-emi API

- **Create/update (double_entry):** auto-creates `accounts` row `type=loan` / `liability_loan`; persists `account_id` + optional `payment_account_id`.
- **`POST /debt/{id}/record-emi`:** body `date`, optional `principal_paise`/`interest_paise` (defaults from amort schedule), optional `payment_account_id` override.
- Posts via `build_emi_payment` + `LedgerService`; interest on `Uncategorized Expense` / category `Debt Interest`.
- Refreshes `current_balance_paise` from `max(0, -account_balance_paise(loan))`; advances `next_emi_date` one month.
- Returns `{ledger_transaction_id}`; `require_ledger_writes` when double_entry.
- Tests: `tests/test_debt_emi_ledger.py` — 4 passed.
- Commit: `feat(debt): loan accounts and record-emi ledger post`
