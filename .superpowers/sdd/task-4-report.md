# Task 4 — ReconciliationService report

Implemented the reconciliation application service:

- Imports normalized statement rows without ledger writes.
- Suggests account/period ledger matches; confirmations, unmatches, ignores, soft-close, reopen, and explicit income/expense adjustments are controlled operations.
- Compares balances through statement period end and closes only when all lines are cleared and balances agree.
- Added close-gate coverage, including an after-period ledger transaction that must not affect the close.

Verification:

- `uv run pytest tests/test_recon_*.py tests/test_ledger_*.py -q`
- `uv run python scripts/ci_check_ledger_writes.py`
