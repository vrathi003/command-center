# Builders

``finance_common.ledger.builders`` turns product intents into balanced
``NewPosting`` tuples. Prefer these over hand-rolled signs.

## Catalogue

| Function | Intent | Legs (simplified) |
|----------|--------|-------------------|
| ``build_bank_expense`` | Debit from bank | Expense ``+``, Bank ``−`` |
| ``build_bank_income`` | Credit to bank | Bank ``+``, Income ``−`` |
| ``build_transfer`` | Move between accounts | To ``+``, From ``−`` |
| ``build_cc_swipe`` | Card purchase (budget spend) | Expense ``+``, CC ``−`` |
| ``build_cc_bill_pay`` | Pay card from bank | CC ``+``, Bank ``−`` |
| ``build_investment_buy`` | Deploy cash to investments | Investment ``+``, Bank ``−`` |
| ``build_investment_sell`` | Redeem to bank | Bank ``+``, Investment ``−`` |
| ``build_emi_payment`` | Loan EMI | Loan ``+principal``, Expense ``+interest``, Bank ``−total`` |

## Who calls them

| Caller | Typical builder |
|--------|-----------------|
| Intake ``plan_postings`` | bank expense/income, cc swipe (not bill pay) |
| Intake ``plan_transfer`` | ``build_transfer`` |
| CC ``pay_bill`` API | ``build_cc_bill_pay`` |
| Debt EMI post | ``build_emi_payment`` |
| Investment record | buy/sell builders |
| Manual / Discord product writes | via intake plan → same builders |

## Important product nuance: CC bill vs swipe

- **Swipe** increases budget spend (expense debit).
- **Bill pay** does **not** add spend again — it only moves liability and cash.

If you post a bill pay as a swipe (or vice versa), utilization and budgets will lie.

## Code

```{eval-rst}
.. automodule:: finance_common.ledger.builders
   :members:
   :undoc-members:
```
