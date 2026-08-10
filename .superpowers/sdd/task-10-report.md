# P3 Migration Acceptance Report

**Branch:** `feature/double-entry-ledger-p3` · **Date:** 2026-08-10

## Verification

- P3 acceptance suite: **95 passed**
  `uv run pytest tests/test_migration_*.py tests/test_transactions_facade.py tests/test_transactions_cutover.py tests/test_intake_*.py tests/test_ledger_*.py -q`
- Ledger write guard: **passed**
  `uv run python scripts/ci_check_ledger_writes.py`
- Full suite: **325 passed**
  `uv run pytest -q --tb=line`

All test runs emitted five PyMuPDF SWIG deprecation warnings; no test failures occurred.

## Operator Dry-Run

The configured `DB_PATH` resolved to `/Users/vrathi/finance/finance.db`, so the migration CLI was run with `--dry-run` only. No `--apply` action was run against the live database.

| Count | Result |
| --- | ---: |
| Migrated | 1,844 |
| Quarantined | 0 |
| Skipped soft-deleted | 4,700 |
| No-op | 0 |

## Remaining Operator Steps

1. Review the dry-run counts and explicitly approve applying to the live database.
2. Run the apply action, then verify Transactions history is served through the ledger facade and a second apply is a no-op.
3. Verify the quarantine desk exposes `needs_opening_balance` for SBI Personal and any other cash/credit-card account needing an opening balance. This cannot be observed from the live dry-run because it reported zero quarantined rows.
