# W1 Credit Cards Ledger Alignment — Acceptance Report

**Branch:** `feature/cc-ledger-alignment-w1` · **Date:** 2026-08-11

## Verification

- W1 CC ledger suite: **10 passed**
  `uv run pytest tests/test_credit_card_pay_bill_ledger.py tests/test_credit_card_live_balance_ledger.py tests/test_credit_card_balance_cache_sync.py tests/test_credit_card_apply_ledger.py -q`
- Ledger write guard: **passed**
  `uv run python scripts/ci_check_ledger_writes.py`
- Full suite: **344 passed**
  `uv run pytest -q`

All pytest runs emitted five PyMuPDF SWIG deprecation warnings; no test failures occurred.

## Scope

W1 delivers double-entry CC bill pay via `build_cc_bill_pay` + `LedgerService.post`, live outstanding from `max(0, -account_balance_paise(liability_cc))`, and `current_balance_paise` cache refresh after pay-bill and statement apply. Legacy engine paths unchanged.

## Spec §4 checklist

| Item | Status |
|------|--------|
| pay_bill → ledger (no `insert_transfer_pair` when double_entry) | ✅ |
| live balance from liability_cc ledger | ✅ |
| cache refresh after apply / pay_bill | ✅ |
| W1 tests (pay, live balance, legacy, CI guard) | ✅ |
| W2/W3 out of scope | ✅ enforced |

## Commits

- `bb1a6cb` feat(cc): pay bill through LedgerService
- `32cbc0b` feat(cc): live balance from liability_cc ledger
- `cf8affd` feat(cc): sync current_balance_paise from ledger

## Known Issues

None within W1 acceptance scope. Debt/EMI (W2), subscription charge posting (W3), and P5 AlertService remain out of scope.
