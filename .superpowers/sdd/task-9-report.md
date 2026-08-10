# Task 9 Report

Implemented quarantine filtering, opening-balance approval, and the Transactions review banner.

- The intake approval API accepts an optional positive `amount_paise` and posts `needs_opening_balance` candidates directly against the system Opening Balance Equity account, with credit-card liabilities inverted.
- The quarantine desk filters pending candidates by migration reason and requires a rupee amount before approving an opening balance.
- Transactions shows a link to the quarantine desk whenever pending candidates exist.

Verification: `uv run ruff check packages/api/src/finance_api/routers/intake.py packages/api/src/finance_api/schemas/intake.py tests/test_intake_api.py`, `uv run pytest tests/test_intake_api.py -q` (6 passed), and `npm --prefix dashboard run build`.
