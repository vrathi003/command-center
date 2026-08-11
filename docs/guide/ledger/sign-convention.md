# Sign convention

All posting amounts are **signed integer paise**. Builder helpers take a **positive
magnitude** and apply signs for you.

## Rules

| Account kind | Increase | Decrease |
|--------------|----------|----------|
| Asset (``asset_*``) | ``+`` (debit) | ``−`` (credit) |
| Liability (``liability_*``) | ``−`` (credit) | ``+`` (debit) |
| Expense | ``+`` (debit) | ``−`` (credit / reverse) |
| Income | ``−`` (credit) | ``+`` (debit / reverse) |

Natural balances:

- Cash / bank / investments: **positive** when you hold money.
- Credit card / loan: **negative** when you owe (liability increase is credit).
- CC **outstanding** shown in the UI is typically ``max(0, −balance)``.

## Quick examples (₹100 = 10000 paise)

**Bank expense**

```text
Expense  +10000
Bank     -10000
```

**CC swipe**

```text
Expense  +10000
CC       -10000     # liability ↑
```

**CC bill pay** (cash-flow only — not a second spend)

```text
CC       +10000     # liability ↓
Bank     -10000
```

**Transfer A → B**

```text
B        +10000
A        -10000
```

**EMI** (principal + interest)

```text
Loan     +principal
Expense  +interest   (category Debt Interest)
Bank     -(principal+interest)
```

Documented in code at the top of ``finance_common.ledger.builders``.
