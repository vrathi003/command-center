# Task 6 Report — Dashboard record flows

**Branch:** `feature/wealth-investments-w1`

## Delivered
- `types/api.ts`: `account_id` on `InvestmentOut` / `FixedIncomeOut`; `RecordInvestmentTradeOut`, `RecordFixedIncomeTradeOut`
- `lib/api.ts`: `recordInvestmentBuy`, `recordInvestmentSell`, `recordFixedIncomeDeposit`, `recordFixedIncomeMaturity`
- `InvestmentsPage.tsx`: Buy/SIP/Sell + FI deposit/maturity modals (Debt/Recurring modal pattern)
- `StocksPortfolioPage.tsx`: Buy/SIP/Sell buttons + shared trade modal
- `npm run build --prefix dashboard` PASS

## UX
- Payment account picker (savings/current/wallet/CC); date + amount + units for trades; maturity payout override optional
