/** Mirrors `finance_common.types` income enums (display strings). */

export const INCOME_TYPES = [
  'Salary',
  'Freelance',
  'Rental',
  'Dividend',
  'Interest',
  'Capital Gains',
  'Bonus',
  'Other',
] as const

export const INCOME_FREQUENCIES = ['monthly', 'quarterly', 'annual', 'one_time'] as const

export const TAXABILITY = ['fully_taxable', 'partially_exempt', 'fully_exempt'] as const
