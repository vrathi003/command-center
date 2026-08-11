# Task 5 — Dashboard Record EMI

**Status:** Complete  
**Commit:** `feat(dashboard): record EMI on debt page`

## Delivered

- Extended `DebtOut` with `account_id` / `payment_account_id`; added `RecordEmiOut` type.
- Added `recordDebtEmi()` → `POST /api/debt/{id}/record-emi`.
- DebtPage: **Record EMI** button on active loans; modal with date, bank select, computed principal/interest split, optional override.

## Verification

`npm run build --prefix dashboard` — passed.
