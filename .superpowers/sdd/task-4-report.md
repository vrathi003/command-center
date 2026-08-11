# Task 4 Report — Dashboard Record charge

**Status:** Done  
**Build:** `npm run build --prefix dashboard` PASS

## Changes
- `SubscriptionOut.account_id`; `RecordChargeOut` type
- `recordSubscriptionCharge()` → POST `/api/subscriptions/{id}/record-charge`
- Active subscription rows: **Record charge** → modal (date, pay-from account, optional amount, remember account)
- Create/edit forms: optional default payment account select
- On success: invalidate `subscriptions`, `transactions`, `dashboard-summary`

## UX
- Modal pattern mirrors DebtPage Record EMI; emerald styling matches Recurring page
