# Debt Live Outstanding · Digests · Uncategorized Queue

**Date:** 2026-08-11  
**Status:** Implemented  

## Scope

1. **Live debt outstanding** — When DE + loan account has posted activity, list/get/summary/dashboard use `max(0, -account_balance_paise)`; else cached `current_balance_paise`.
2. **Digests via AlertService** — Weekly/monthly jobs already use DE lenses; also emit `digest.weekly` / `digest.monthly` for in-app alerts; Discord DM unchanged when configured. Bot `/balance` uses ledger spend totals under DE.
3. **Uncategorized queue** — Under DE, group by `ledger_transactions.payee` with expense posting category `Other`; statement-import merge unchanged.
