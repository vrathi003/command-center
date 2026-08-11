# Card EMI conversion (e-commerce)

## Scenario

You buy something for ₹X on a credit card with **EMI / convert to EMI**:

1. Statement shows a **debit** (purchase) of ₹X.
2. Statement shows a **credit** of ₹X when the purchase is converted to EMI
   (revolving balance drops; principal moves into an EMI plan).
3. Later months show EMI instalments.

## What the product does today

| Piece | Behaviour |
|-------|-----------|
| Intake / quarantine on the **credit** | Treated like “money in on CC” → planner error *Credit-card payment needs a bank account* unless you force a bank→card transfer (usually **wrong** for conversion). |
| Credit Card → **EMI plans** | Manual tracker: limit blocked, monthly EMI, optional Track in Debts. **Not** auto-linked to the conversion credit. |
| Loan ``build_emi_payment`` | For **loan accounts**, not card EMI conversion credits. |

## Recommended operator handling (current)

1. Ensure the **original purchase** is posted as a normal **CC swipe** (expense + CC liability).
2. For the **conversion credit** in Email Inbox / Quarantine → **Reject** (or leave rejected).
   Posting it as income or as a bank transfer will distort books.
3. Add / update an **EMI plan** on the card detail page for principal, tenure, monthly EMI, limit blocked.

## Why “I selected a bank account” still failed

If Account override still shows a **credit card** (e.g. “ICICI Bank Credit Card”), the
planner still sees ``liability_cc`` + direction ``in``. The word “Bank” in the card name
does not make it ``asset_cash``.

Even if you pick a real savings account **without** “Approve as transfer,” the planner
would treat it as **bank income**, which is also wrong for a conversion credit.

## Future improvement (not built)

A dedicated **“EMI conversion”** approve action could:

- leave the expense intact,
- reverse only the revolving CC liability leg (or reclass to an EMI liability account),
- link/create a ``credit_card_emis`` row.

Until that exists, use the reject + EMI plan workflow above.
