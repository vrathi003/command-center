# Task 7 report

- Cutover transaction edits now validate the complete replacement posting before the existing transaction is voided.
- Same-account transfer edits and incomplete transfer account pairs return HTTP 422 without voiding the existing transaction.
- A replacement posting failure after a successful void returns HTTP 500 with a recovery-oriented message.
- Legacy-engine imports return HTTP 410 after cutover, directing callers to the double-entry import with `account_id`.
- Regression coverage: `uv run pytest tests/test_transactions_cutover.py tests/test_transactions_import.py -q`.
