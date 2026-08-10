# Task 4 Reconciliation Review Fix

- Confirmed matches now require the statement account posting to use the exact
  signed amount implied by the statement line: `out` is negative and `in` is
  positive.
- Match suggestions apply the same signed amount requirement before scoring.
- The existing ledger builder tests verify credit-card swipes post `-amount`
  to the liability account and bill payments post `+amount`.
- Added regressions for opposite-direction candidates and manual confirmation.
