# Worked examples

Amounts in paise. Signs follow {doc}`sign-convention`.

## 1. Swipe ₹540 on Food (HDFC CC)

```text
Expense:Food     +54000
HDFC CC          -54000
```

Builder: ``build_cc_swipe``. Budget spend += ₹540. CC outstanding += ₹540.

## 2. Pay ₹10,000 CC bill from savings

```text
HDFC CC          +1000000   # liability ↓
Savings          -1000000
```

Builder: ``build_cc_bill_pay``. Budget spend unchanged. Outstanding ↓ ₹10,000.

## 3. UPI grocery ₹800 from bank

```text
Expense:Food     +80000
Bank             -80000
```

Builder: ``build_bank_expense``.

## 4. Salary ₹1,00,000

```text
Bank             +10000000
Income           -10000000
```

Builder: ``build_bank_income``.

## 5. Transfer ₹5,000 wallet ← bank

```text
Wallet           +500000
Bank             -500000
```

Builder: ``build_transfer``. Excluded from budget spend.

## 6. Loan EMI ₹25,000 (₹18k principal + ₹7k interest)

```text
Loan             +1800000
Expense:Debt Interest +700000
Bank             -2500000
```

Builder: ``build_emi_payment``.

## 7. Idempotent email re-approve

Same ``external_key='gmail:…'`` on second ``post`` → returns existing id, no second legs.

## 8. Mistake correction

1. ``void(tx_id)``
2. ``post`` a corrected plan

Do not soft-delete ledger postings; void is the audit-friendly reverse switch.
