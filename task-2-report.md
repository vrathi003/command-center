# Task 2 Email Staging Review Fix

- `set_status` now uses `_UNSET` sentinel for `created_transaction_id`, `ledger_transaction_id`, and `intake_candidate_id`: omitted kwargs leave existing links unchanged; explicit `None` clears.
- Dynamic UPDATE builds SET clauses only for provided link fields; `status` is always updated.
- Added regressions: `test_set_status_omitted_intake_candidate_id_preserves_existing_link`, `test_set_status_omitted_ledger_transaction_id_preserves_existing_link`.
- All 8 tests in `tests/test_email_staging_repo.py` pass.
