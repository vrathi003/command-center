# LedgerService (``service.py``)

The only persistence API that should create ledger rows.

## ``post(conn, inp: PostTransactionInput) -> int``

1. If ``external_key`` already exists → return existing id (**idempotent**).
2. Validate postings (≥2, integer paise, sum 0, no zeros).
3. ``BEGIN IMMEDIATE``.
4. Load ``account_class`` for every posting account; fail if unknown ids.
5. Require category on expense/income postings.
6. Insert header + postings; ``commit``.
7. Return new ``transaction_id``.

On any failure after begin → ``rollback`` and re-raise.

### Input shape

```python
PostTransactionInput(
    tx_date=date(2026, 8, 11),
    postings=(
        NewPosting(expense_id, 5400_00, "Shopping"),
        NewPosting(cc_id, -5400_00),
    ),
    payee="Amazon",
    source="email",
    external_key="gmail:msg123",
)
```

## ``void(conn, transaction_id)``

Sets ``status='void'`` only if currently ``posted``. Postings remain.
Balances and spend queries filter ``status = 'posted'``.

## ``get_transaction`` / ``list_transactions``

Read helpers. Listing is newest-first; ``include_void`` defaults false.

## Errors

| Exception | When |
|-----------|------|
| ``UnbalancedTransactionError`` | Sum of postings ≠ 0 |
| ``LedgerError`` | Structure / account / category / void races |
| ``DuplicateExternalKeyError`` | Reserved for callers that want strict fail-on-dupe (idempotent path returns id instead) |

## Code

```{eval-rst}
.. automodule:: finance_common.ledger.service
   :members: post, void, get_transaction, list_transactions
   :undoc-members:
   :show-inheritance:
```
