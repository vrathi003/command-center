# P2 Acceptance Report

**Branch:** `feature/double-entry-ledger-p2`  
**Date:** 2026-08-10

## Verification

- P2 acceptance suite: **103 passed**  
  `uv run pytest tests/test_intake_*.py tests/test_ledger_*.py tests/test_transactions_import.py tests/test_email_inbox_ledger.py tests/test_credit_card_apply_ledger.py -v`
- Ledger write guard: **passed**  
  `uv run python scripts/ci_check_ledger_writes.py`
- Full suite: **287 passed**  
  `uv run pytest -q --tb=line`

## Regression Fixed

P2 routes statement imports through the double-entry intake path by default, which correctly requires
an `account_id`. Merchant-rule tests intentionally exercise the legacy `transactions` table, so their
CSV helper now explicitly selects `ledger_engine: legacy` before importing.

## Smoke Notes

- No test skips.
- All runs emitted five pre-existing PyMuPDF SWIG deprecation warnings; no test failures remain.
