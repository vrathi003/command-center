# Debt EMI

## Manual Record EMI

1. **Debt** page → active loan → **Record EMI**.
2. Confirm payment (bank/wallet) account, date, optional principal/interest override.
3. Server builds ``build_emi_payment`` and posts.

## Auto EMI job

On due day, if loan account + payment account + EMI amount are configured, a background
job posts the same pattern and advances ``next_emi_date``. Otherwise you get a reminder
alert / Discord DM (when configured).

## Ledger effect

```text
Loan liability   +principal
Expense          +interest   (Debt Interest)
Bank             -(principal+interest)
```

Outstanding follows the loan account’s posted balance (live path under DE).

## Related

- Credit-card **EMI plans** on the card detail page are a **separate tracker** (limit
  blocked / monthly dues). They are not the same as loan ``build_emi_payment`` posts.
- See {doc}`emi-conversion` for e-commerce “convert to EMI” statement credits.
