# W2 Net Worth — Acceptance Report
**Branch:** `feature/wealth-net-worth-w2` · **Date:** 2026-08-11

## Verification
- W2 suite: **5 passed** (`tests/test_net_worth_composed.py`)
- Ledger write guard: **passed** (`make check-ledger-writes`)
- Full suite: **453 passed** (`uv run pytest tests/test_net_worth_composed.py tests/ -q --tb=line`)

## Scope
Composed net worth lens when `ledger_engine=double_entry`: `net_worth_totals` minus linked inv/FI ledger cost plus MV/principal overlay and real assets; unbound debt/CC add-ons for liabilities. `compute_totals_from_holdings` dispatches composed vs legacy holdings-only. Snapshot API and month-end job unchanged (already call dispatcher).

## Spec §6 checklist
Composed compute ✅ · snapshots/job via dispatcher ✅ · legacy path preserved ✅ · W3 Income next ✅

## Known Issues
None. Cash completeness note: unlinked bank accounts remain off NW until opening-seeded (documented in spec §6.3).
