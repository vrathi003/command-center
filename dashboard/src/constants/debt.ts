/** Mirrors `finance_common.types.DebtType` and `DebtStatus`. */

export const DEBT_TYPES = [
  'Home Loan',
  'Car Loan',
  'Personal Loan',
  'Education Loan',
  'Credit Card Revolving',
  'Other',
] as const

export const DEBT_STATUS = ['active', 'closed', 'paused'] as const
