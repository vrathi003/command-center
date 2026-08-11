# Discord Bot — Double-Entry Writes Design

**Date:** 2026-08-11  
**Status:** Approved  
**Owner:** Vaibhav  
**Depends on:** API transaction write gate (`uses_ledger_books`)

---

## 1. Goal

When `ledger_engine == double_entry`, Discord `/log`, transfer flow, `/edit`, `/undo`, and ❌ reactions write through `LedgerService` so bot entries appear in dashboard ledger reads. Legacy engine keeps today’s `transactions` repo path.

## 2. Locked decisions

| Topic | Choice |
|-------|--------|
| Approach | Branch at bot persist helpers (mirror API), not disable Discord |
| Missing debit/credit `account_id` | **Refuse** with a clear message (no forced picker) |
| Transfer under DE | One ledger transaction; footer `id=N` (not `ids=A+B`) |
| Edit under DE | Void + repost; reply footer uses **new** id |
| Shared code | Thin helpers in `finance_common.ledger.product_writes` (no HTTPException) |

## 3. Behavior matrix

| Surface | DE | Legacy |
|---------|----|--------|
| Log / template debit·credit | Require `account_id` → `plan_postings` + `post`; `source="discord"`; optional `external_key=discord:{msg_id}` | `insert_transaction` |
| Transfer | `plan_transfer` + `post` | `insert_transfer_pair` |
| `/edit` | Load ledger tx (source=discord, not transfer) → void + post | `update_transaction_fields` |
| `/undo` / ❌ | `void` last/target posted discord tx | soft-delete |

## 4. Out of scope

- Bot `/balance` ledger lenses (separate read-model follow-up)
- Forcing account reaction picker for missing account
- Refactoring API routers to call `product_writes` (optional later)

## 5. Tests

- DE without cutover: persist debit → ledger row, zero legacy `transactions`
- Missing account → refusal string, no ledger row
- Transfer → one ledger id
- Void last / by id
- Legacy engine: existing insert/soft-delete path still used
