# Overview

## Package layout

Code lives under ``packages/common/src/finance_common/ledger/``:

| Module | Responsibility |
|--------|----------------|
| ``models.py`` | ``NewPosting``, ``PostTransactionInput``, ``PostedTransaction`` |
| ``builders.py`` | Common patterns (expense, income, CC swipe, bill pay, transfer, EMI, …) |
| ``service.py`` | ``post``, ``void``, ``get_transaction``, ``list_transactions`` |
| ``balances.py`` | Account balances + net-worth totals from posted postings |
| ``reports.py`` | Budget spend lenses (by category / account / cash-flow) |
| ``integrity.py`` | Detect unbalanced posted transactions |
| ``product_writes.py`` | Dashboard/bot-shaped plan+post helpers |
| ``errors.py`` | ``LedgerError``, ``UnbalancedTransactionError``, … |

API surface: ``packages/api/src/finance_api/routers/ledger.py`` (pattern-based post).
Product routes (transactions, email, CC, debt) call builders + ``service.post`` themselves.

## Invariants

1. **At least two postings** per transaction.
2. **Signed amounts sum to zero** (enforced in ``service.post`` before commit).
3. **No zero-amount postings**.
4. **Expense / income legs require a non-empty category**.
5. **Immutability of postings** — corrections use ``void``, then a new ``post``.
6. **Idempotent external keys** — same ``external_key`` returns the existing tx id (no duplicate insert).

## Status lifecycle

```text
  post() ──► status = 'posted'
                │
             void()
                │
                ▼
           status = 'void'   (postings retained for audit; excluded from balances)
```

There is no hard-delete of ledger rows in normal product flows.

## Relationship to other domains

| Domain | How it uses the ledger |
|--------|------------------------|
| Intake / Email | Plans candidate → ``post``; quarantine when ambiguous |
| Reconciliation | Matches statement lines to ledger txs (control book) |
| Budget | Reads expense debits via ``reports.budget_spend_*`` |
| Credit cards | Swipes / bill pays post; live outstanding = −liability balance |
| Debt | EMI posts principal + interest; outstanding from loan account |
| Alerts | Observes domain events; does not write the ledger |

See {doc}`../workflows/index` for end-to-end operator paths.
