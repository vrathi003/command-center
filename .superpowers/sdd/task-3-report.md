## Task 3 — Suggest matcher

Implemented a pure reconciliation matcher with deterministic, per-line proposals. It requires the same account, absolute amount equality, a configurable date window, and awards a payee-prefix bonus while excluding confirmed ledger transactions.

Added golden tests for selecting the best candidate, excluding matched/ineligible candidates, and scoring date distance with absent payees.

Validation:
- `uv run pytest tests/test_recon_schema.py tests/test_recon_repository.py tests/test_recon_suggest.py -q` — 6 passed
- `uv run ruff check packages/common/src/finance_common/recon/suggest.py tests/test_recon_suggest.py` — passed
- `uv run mypy packages/common/src/finance_common/recon/suggest.py` — passed
