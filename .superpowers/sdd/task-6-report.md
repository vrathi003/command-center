# Task 6 — Dashboard Reconciliation page

## Delivered

- Added `/reconciliation` navigation and route.
- Added an account-scoped statement workspace with statement selection, statement lines, suggestions, unmatched ledger entries, confirmation, ignore, manual matching, explicit adjustments, and soft-close/reopen controls.
- Added typed reconciliation and ledger API clients.

## Verification

`npm run build` passed after installing the lockfile dependencies with `npm ci`.

## Notes

- Existing `uv.lock` changes were left uncommitted.
