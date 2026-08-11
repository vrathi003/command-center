# Task 5 Report — FI deposit / maturity APIs

**Branch:** `feature/wealth-investments-w1`

## Delivered
- `record_fixed_income_deposit` / `record_fixed_income_maturity` in `investment_ledger.py` (reuse `build_investment_buy` / `build_investment_sell`)
- `POST /fixed-income/{id}/record-deposit` and `record-maturity` in `fixed_income.py` (double_entry + ledger writes required)
- Schemas: `RecordFixedIncomeDepositBody`, `RecordFixedIncomeMaturityBody`, `RecordFixedIncomeTradeOut`
- Tests: 4 new cases in `test_investment_ledger_w1.py` (11 total passed)

## Behavior
- Deposit: Dr FI asset · Cr bank; `principal_paise += amount`
- Maturity: Dr bank · Cr FI asset; `principal_paise = max(0, principal − amount)`; default amount = current principal
