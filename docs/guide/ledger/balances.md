# Balances and reports

## Account balance

``account_balance_paise(conn, account_id, as_of=None)``

Sum of ``ledger_postings.amount_paise`` for that account where the parent
transaction ``status = 'posted'`` (and optionally ``date <= as_of``).

Voided transactions contribute **nothing**.

## Net worth

``net_worth_totals(conn, as_of=None) → (assets, liabilities, net)``

- Assets: sum of postings on ``account_class LIKE 'asset_%'``
- Liabilities: ``−`` sum on ``liability_%`` (so a negative CC balance becomes a positive liability)
- Net = assets − liabilities

## Budget / spend lenses (``reports.py``)

| Function | Meaning |
|----------|---------|
| ``budget_spend_by_category`` | Expense account debits (``amount_paise > 0``) by category |
| ``budget_spend_total`` | Same, single total |
| ``budget_spend_by_account`` | Attributes those expense debits to the funding cash/CC leg in the same tx |

Transfers and pure investment buys (no expense leg) are excluded from budget spend.

## UI mapping

| Screen | Ledger read |
|--------|-------------|
| Dashboard spend KPIs | budget spend totals (when books cut over) |
| Budget vs actual | category spend |
| CC live outstanding | ``max(0, −account_balance(cc))`` |
| Debt outstanding | loan liability balance (live path) |
| Net worth | ``net_worth_totals`` / holdings hybrids as configured |

## Code

```{eval-rst}
.. automodule:: finance_common.ledger.balances
   :members:
```
