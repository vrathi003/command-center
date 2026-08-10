# Task 6 Report: Ledger Transactions Facade

- Added a cutover-aware ledger-to-legacy transaction facade for transaction list and detail reads.
- Maps debit, credit, and transfer entries to the existing `TransactionRow` response shape.
- Preserves legacy reads before cutover; ledger responses use `payment_mode: "Other"`.
- Added API coverage for debit, credit, and transfer mappings.

Verification: `uv run pytest tests/test_transactions_facade.py tests/test_ledger_api.py -q` (11 passed); Ruff and mypy passed.
