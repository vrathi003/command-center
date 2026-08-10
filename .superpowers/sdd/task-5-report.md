# Task 5 — HTTP API for reconciliation

Implemented `/api/recon` reconciliation endpoints: statement listing and JSON/multipart creation, workspace retrieval, suggestions, matching controls, explicit ledger adjustments, and reversible soft-close controls. Multipart imports accept `account_id`, `period`, opening/closing balances, and CSV/XLSX/XLS/PDF files; tabular files reuse the existing upload loader and PDF files reuse the statement parser before `ReconciliationService.import_rows`.

`/adjust` is guarded with `require_ledger_writes`; other reconciliation controls do not write to the ledger.

Verification: `uv run pytest tests/test_recon_api.py tests/test_recon_service.py tests/test_recon_repository.py tests/test_recon_suggest.py -q` — 10 passed. The API tests exercise multipart import, list/workspace retrieval, suggestions, confirm/unmatch/ignore, soft-close/reopen, adjustment posting, and the ledger-write gate.

`uv run mypy` still reports pre-existing strict-type errors in `finance_common.repositories.recon` and `merchant_rules`; the new router-specific password handling is type-safe.
