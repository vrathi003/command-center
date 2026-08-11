# Merchant Rules + Budget Rename — Ledger Alignment

**Date:** 2026-08-11  
**Status:** Approved (implementer proceed from sweep)  
**Depends on:** `uses_ledger_books` / write gate

## Locked decisions

| Topic | Choice |
|-------|--------|
| Merchant retroactive apply under DE | Match `ledger_transactions.payee`; update expense/income `ledger_postings.category` + canonicalize `payee` |
| Budget rename under DE | Also `UPDATE ledger_postings SET category` (all matching postings) |
| Legacy path | Unchanged when `ledger_engine=legacy` |
| Statement-import snapshot | Always apply (engine-agnostic) |
| Uncategorized queue DE | Out of scope (follow-up) |
| `merchant_rules.category` on rename | Update for consistency |

No void/repost — in-place category updates match how lenses/facade already read.
