# Credit card bill pay

## Operator steps

1. Open **Credit Cards** → card detail.
2. **Pay bill** — choose **bank** account, amount, date.
3. API posts via ``build_cc_bill_pay`` + ``ledger.service.post``.

## Ledger effect

```text
CC account     +amount   # liability decreases
Bank account   -amount   # cash decreases
```

- **Not** budget spend.
- Live outstanding should drop by the paid amount.
- Cached ``current_balance_paise`` on the card is refreshed from the ledger after apply/pay paths.

## Contrast with swipe

| Action | Expense? | Liability | Cash |
|--------|----------|-----------|------|
| Swipe | Yes | ↑ | — |
| Bill pay | No | ↓ | ↓ |

## Do not confuse with

- Quarantine “CC in” without transfer (will error).
- Category **CC Bill** on a card credit — category alone does not switch builders; account class + direction / transfer flag does.
