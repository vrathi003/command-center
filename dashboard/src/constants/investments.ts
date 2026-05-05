/** Mirrors `finance_common.types.InvestmentType` and `FixedIncomeType`. */

export const INVESTMENT_TYPES = [
  'Mutual Fund',
  'Stock',
  'ETF',
  'Sovereign Gold Bond',
  'REIT',
  'Other',
] as const

export const FIXED_INCOME_TYPES = [
  'Fixed Deposit',
  'Recurring Deposit',
  'PPF',
  'NPS',
  'EPF',
  'NSC',
  'Sukanya Samriddhi',
  'Other',
] as const
