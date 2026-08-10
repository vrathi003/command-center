# Task 6 — Dashboard Reconciliation page

## Delivered

- Added `/reconciliation` navigation and route.
- Added an account-scoped statement workspace with statement selection, statement lines, suggestions, unmatched ledger entries, confirmation, ignore, manual matching, explicit adjustments, and soft-close/reopen controls.
- Added typed reconciliation and ledger API clients.

## Verification

`npm run build` passed after installing the lockfile dependencies with `npm ci`.

## Notes

- Existing `uv.lock` changes were left uncommitted.
# Task 6 Report: Ledger Transactions Facade

- Added a cutover-aware ledger-to-legacy transaction facade for transaction list and detail reads.
- Maps debit, credit, and transfer entries to the existing `TransactionRow` response shape.
- Preserves legacy reads before cutover; ledger responses use `payment_mode: "Other"`.
- Added API coverage for debit, credit, and transfer mappings.

Verification: `uv run pytest tests/test_transactions_facade.py tests/test_ledger_api.py -q` (11 passed); Ruff and mypy passed.

Review follow-up:
- Moved account-name and account-id filtering into the posted-ledger SQL query before ordering and `LIMIT`.
- Detail reads now treat void ledger entries as not found and always include `transfer_sibling: null` for cutover compatibility.
- Added regression coverage for filter order, void detail reads, and transfer sibling response shape.

Verification: `uv run pytest tests/test_transactions_facade.py tests/test_transactions_update.py -q` (11 passed); `uv run ruff check packages/common/src/finance_common/migration/facade.py packages/api/src/finance_api/routers/transactions.py tests/test_transactions_facade.py` (passed).
