# Transfers

Internal moves between accounts (bank ↔ bank, bank ↔ wallet, bank → CC bill, etc.).

## Product entry points

| Surface | How |
|---------|-----|
| Transactions drawer | Type **Transfer**, from + to |
| Discord | Transfer parse / template |
| Email Inbox | Approve as transfer (debit + credit legs) |
| Quarantine | **Approve as transfer** checkbox |

## Ledger

Always ``build_transfer``:

```text
To account     +amount
From account   -amount
```

No expense/income legs → **excluded from budget spend**.

## Rules of thumb

- Paying a credit card from a bank is a transfer (or dedicated bill-pay builder — same
  economic signs as ``build_cc_bill_pay``).
- Do not mark lifestyle spend as a transfer to “hide” it from budgets.
- Transfer templates still need a **to** account at apply time.
