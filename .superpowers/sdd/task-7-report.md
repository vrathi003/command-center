# W1 Investments + Fixed Income — Acceptance Report
**Branch:** `feature/wealth-investments-w1` · **Date:** 2026-08-11

## Verification
- W1 suite: **11 passed** (`tests/test_investment_ledger_w1.py`)
- Ledger write guard: **passed** (`make check-ledger-writes`)
- Full suite: **449 passed** (`uv run pytest tests/ -q --tb=line`)

## Scope
`account_id` on investments/FI, idempotent opening seed, Record buy/SIP/sell and FI deposit/maturity via `LedgerService`, dashboard record modals. Buys are transfers excluded from budget spend.

## Spec §5 checklist
account_id + seed ✅ · sell/buy builders ✅ · record APIs ✅ · dashboard ✅ · W2/W3 out of scope ✅

## Known Issues
None. W2 Net Worth (composed lens) is next.
