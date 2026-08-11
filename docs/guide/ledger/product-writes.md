# Product writes

``finance_common.ledger.product_writes`` is the shared “plan then post” helper used by
the Discord bot under double-entry. The HTTP API often duplicates the same pattern
inline (intake plan / builders + ``ledger.service.post``).

## ``post_manual``

1. Require ``account_id`` (error copy explains DE needs an account).
2. Build an intake ``Candidate`` with ``direction`` from debit/credit.
3. ``plan_postings`` → ``PostTransactionInput``.
4. ``ledger.service.post``.

Maps:

| UI / bot type | Direction | Planner path |
|---------------|-----------|--------------|
| debit | ``out`` | bank expense or CC swipe |
| credit | ``in`` | bank income — **or** error on CC (“needs a bank account”) |

That last row is why a **CC payment / EMI conversion credit** cannot be approved as a
plain credit on the card. See {doc}`../workflows/emi-conversion`.

## ``post_transfer``

Uses ``plan_transfer`` → ``build_transfer`` → ``post``.

## ``void_posted``

Thin wrapper over ``ledger.service.void`` with ``ProductWriteError`` mapping.

## Errors

``ProductWriteError`` — safe to show to the user / Discord. Wraps ``IntakePlanError``
and ``LedgerError``.
