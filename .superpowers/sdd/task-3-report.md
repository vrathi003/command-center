# Task 3 Report — record-charge ledger post

**Status:** Done  
**Commit:** (see parent return)  
**Tests:** 4 passed in `tests/test_subscription_charge_ledger.py`

## Delivered
- `subscription_charge.py`: `post_subscription_charge`, `advance_billing_date`, `uncategorized_expense_id`
- Schemas: `RecordChargeBody`, `RecordChargeOut`
- Route: `POST /subscriptions/{id}/record-charge` (201, double_entry only)
- Ledger: `build_bank_expense` / `build_cc_swipe`, source `subscription`, advances `next_billing_date`

## Coverage
- Bank charge reduces asset / increases expense; monthly advance
- CC swipe credits liability; default category `Subscriptions`
- Missing account → 422; legacy engine → 422; no legacy `transactions` rows

## Out of scope
- Task 4 dashboard UI; Task 5 acceptance; `uv.lock`
