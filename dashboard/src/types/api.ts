export type DashboardSummary = {
  current_fy: string
  spent_today_paise: number
  spent_week_paise: number
  spent_month_paise: number
  spent_by_category_month: Record<string, number>
  spent_by_account_month: Record<string, number>
  total_debt_paise: number
  net_worth_paise: number | null
  portfolio_value_paise: number
  monthly_income_paise: number | null
  savings_rate_month: number | null
}

export type AccountOut = {
  id: number
  name: string
  type: string
  institution: string | null
  currency: string
  is_active: boolean
}

export type DashboardAlerts = {
  alerts: Array<{
    kind: string
    message: string
    severity: string
  }>
}

export type TransactionRow = {
  id: number
  date: string
  amount_paise: number
  category: string
  merchant: string | null
  payment_mode: string
  account: string | null
  notes: string | null
  transaction_type: 'debit' | 'credit' | 'transfer'
  source: string
  account_id?: number | null
  transfer_pair_id?: string | null
  tags?: string | null
}

/** `GET /transactions/{id}` — same fields as a list row plus optional transfer leg. */
export type TransactionDetailOut = TransactionRow & {
  transfer_sibling: TransactionRow | null
}

export type TransferCreateResponse = {
  transfer_pair_id: string
  debit_transaction_id: number
  credit_transaction_id: number
}

export type TransactionImportResult = {
  imported: number
  failed: number
  errors: Array<{ row: number; message: string }>
}

export type TransactionTemplateOut = {
  id: number
  name: string
  amount: number | null
  merchant: string | null
  category: string | null
  account_id: number | null
  payment_mode: string | null
  transaction_type: 'debit' | 'credit' | 'transfer'
  notes: string | null
  tags: string | null
  created_at: string
}

export type BudgetVsActualRow = {
  category: string
  budget_paise: number | null
  spent_paise: number
  pct_of_budget: number | null
  status: 'none' | 'ok' | 'warn' | 'over' | 'full'
}

export type BudgetVsActualResponse = {
  fy: string
  month: string
  rows: BudgetVsActualRow[]
}

export type DebtOut = {
  id: number
  name: string
  lender: string | null
  type: string
  original_amount_paise: number | null
  current_balance_paise: number
  emi_paise: number | null
  rate_percent: number | null
  start_date: string | null
  next_emi_date: string | null
  status: string
  tenure_months: number | null
  first_emi_date: string | null
  full_emi_start_date: string | null
}

export type LoanDisbursalOut = {
  id: number
  debt_id: number
  disbursal_date: string
  amount_paise: number
  cumulative_paise: number
  notes: string | null
  created_at: string
}

export type DebtSummaryOut = {
  total_outstanding_paise: number
  total_emi_monthly_paise: number
  active_count: number
  next_emi_date: string | null
  next_emi_debt_name: string | null
}

export type SubscriptionOut = {
  id: number
  name: string
  provider: string | null
  category: string | null
  amount_paise: number
  billing_cycle: string
  monthly_equivalent_paise: number
  next_billing_date: string | null
  notes: string | null
  is_active: boolean
}

export type CreditCardOut = {
  id: number
  name: string
  issuer: string | null
  last_four: string | null
  credit_limit_paise: number
  current_balance_paise: number | null
  notes: string | null
  is_active: boolean
  utilization_pct: number | null
  emi_limit_blocked_paise: number
  emi_monthly_due_paise: number
  emi_active_plan_count: number
  total_limit_used_paise: number
}

export type CreditCardEmiOut = {
  id: number
  credit_card_id: number
  description: string
  limit_blocked_paise: number
  emi_amount_paise: number
  tenure_months: number
  installments_paid: number
  is_active: boolean
  notes: string | null
  loan_type: string | null
  creation_date: string | null
  finish_date: string | null
  principal_paise: number | null
  outstanding_instalment_paise: number | null
  installments_remaining: number
  pending_installments: number
  principal_basis_paise: number
  total_repayment_schedule_paise: number
  total_interest_estimated_paise: number
  interest_over_principal_pct: number | null
  amount_paid_to_date_paise: number
  interest_paid_estimated_paise: number
  interest_remaining_estimated_paise: number
}

export type CreditCardStatementOut = {
  id: number
  credit_card_id: number
  filename: string
  period_start: string | null
  period_end: string | null
  extraction_preview: string | null
  summary: Record<string, unknown>
  line_items: Array<Record<string, unknown>>
  status: string
  created_at: string | null
}

export type CreditCardStatementApplyResponse = {
  imported_count: number
  updated_balance_paise: number | null
}

export type AmortizationRow = {
  month_index: number
  payment_paise: number
  interest_paise: number
  principal_paise: number
  balance_after_paise: number
  phase: 'pre_emi' | 'full_emi'
}

export type AmortizationResponse = {
  debt_id: number
  rows: AmortizationRow[]
  payoff_months: number | null
  is_phased: boolean
  total_pre_emi_months: number
  total_disbursed_paise: number | null
}

export type InvestmentOut = {
  id: number
  instrument: string
  type: string
  isin_code: string | null
  units: number | null
  avg_price_paise: number | null
  current_price_paise: number | null
  last_synced: string | null
  sector: string | null
  equity_tax_class: string
  cost_basis_paise: number | null
  market_value_paise: number | null
  unrealized_paise: number | null
}

export type PortfolioSummaryOut = {
  cost_basis_paise: number
  market_value_paise: number
  unrealized_paise: number
  holdings_count: number
}

export type FixedIncomeOut = {
  id: number
  institution: string
  type: string
  principal_paise: number
  rate_percent: number | null
  start_date: string | null
  maturity_date: string | null
}

export type FixedIncomeSummaryOut = {
  total_principal_paise: number
  instrument_count: number
}

export type NetWorthSnapshotOut = {
  id: number
  snapshot_date: string
  total_assets_paise: number
  total_liabilities_paise: number
  net_worth_paise: number
}

export type GoalOut = {
  id: number
  name: string
  category: string | null
  target_amount_paise: number
  current_amount_paise: number
  monthly_contribution_paise: number | null
  target_date: string | null
  progress_pct: number | null
}

export type HomeInventorySummaryOut = {
  item_count: number
  purchase_value_total_paise: number
  service_spend_total_paise: number
  count_by_category: Record<string, number>
  warranty_expiring_within_90_days: number
}

export type HomeItemSummaryOut = {
  id: number
  name: string
  category: string
  brand: string | null
  model: string | null
  room_location: string | null
  purchase_date: string | null
  purchase_price_paise: number | null
  warranty_end_date: string | null
  condition_status: string
  service_event_count: number
  total_service_spend_paise: number
}

export type HomeItemOut = {
  id: number
  name: string
  category: string
  brand: string | null
  model: string | null
  serial_number: string | null
  room_location: string | null
  purchase_date: string | null
  purchase_price_paise: number | null
  retailer: string | null
  warranty_end_date: string | null
  extended_warranty: boolean
  condition_status: string
  notes: string | null
  created_at: string
  updated_at: string
}

export type HomeItemServiceEventOut = {
  id: number
  home_item_id: number
  service_date: string
  event_type: string
  vendor: string | null
  description: string | null
  cost_paise: number | null
  next_service_due: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export type IncomeOut = {
  id: number
  name: string
  type: string
  amount_paise: number | null
  frequency: string
  taxability: string
  is_active: boolean
  monthly_equivalent_paise: number
}

export type IncomeSummaryOut = {
  stream_count: number
  total_monthly_equivalent_paise: number
}

export type SettingsOut = {
  current_fy: string
  tax_regime: string | null
  tax_80c_annual_paise: number | null
  tax_80d_annual_paise: number | null
}

export type FYSpendingReport = {
  fy: string
  rows: Array<{
    fy_month: number
    label: string
    start_date: string
    end_date: string
    spent_paise: number
  }>
  total_spent_paise: number
}

export type FYSummaryReport = {
  fy: string
  total_spent_paise: number
  total_monthly_income_run_rate_paise: number
  implied_savings_paise: number
}

// ── Assets ──────────────────────────────────────────────────────────────────

export type AssetOut = {
  id: number
  name: string
  type: string  // apartment | plot | commercial | vehicle | gold | other
  status: string  // active | sold
  purchase_date: string | null
  purchase_price_paise: number | null
  current_value_paise: number | null
  ownership_percent: number
  co_owner: string | null
  notes: string | null
}

export type RealEstateOut = {
  asset_id: number
  address: string | null
  city: string | null
  state: string | null
  pin_code: string | null
  builder: string | null
  project_name: string | null
  unit_details: string | null
  carpet_area_sqft: number | null
  builtin_area_sqft: number | null
  super_builtin_area_sqft: number | null
  purchase_psf_paise: number | null
  current_psf_paise: number | null
  psf_area_type: string  // carpet | builtin | super_builtin
  possession_status: string  // under_construction | possessed | na
  possession_date_estimated: string | null
  possession_date_actual: string | null
  agreement_value_paise: number | null
  circle_rate_psf_paise: number | null
}

export type VehicleOut = {
  asset_id: number
  make: string | null
  model: string | null
  variant: string | null
  year: number | null
  registration_number: string | null
  fuel_type: string | null
  color: string | null
  depreciation_rate_percent: number
}

export type AssetCostOut = {
  id: number
  asset_id: number
  cost_type: string
  description: string | null
  amount_paise: number
  paid_date: string | null
  is_paid: boolean
}

export type AssetLoanOut = {
  id: number
  asset_id: number
  debt_id: number
  debt_name: string
  sanctioned_amount_paise: number | null
  disbursed_amount_paise: number | null
  remaining_to_disburse_paise: number | null
  pre_emi_paise: number | null
  final_emi_paise: number | null
  notes: string | null
}

export type AssetPaymentOut = {
  id: number
  asset_id: number
  milestone: string | null
  amount_paise: number
  amount_cash_paise: number
  amount_loan_paise: number
  payment_date: string
  reference_number: string | null
  notes: string | null
  is_paid: boolean
  due_date: string | null
  paid_date: string | null
  fund_source: 'cash' | 'bank_loan'
}

export type AssetDetailOut = {
  asset: AssetOut
  real_estate: RealEstateOut | null
  vehicle: VehicleOut | null
  costs: AssetCostOut[]
  loans: AssetLoanOut[]
  payments: AssetPaymentOut[]
  /** Sum of cost breakdown rows + payment milestone totals (cash + loan). */
  total_cost_paise: number
  total_paid_paise: number
  total_payment_milestones_upcoming_paise: number
  appreciation_pct: number | null
}

export type AssetSummaryOut = {
  total_assets: number
  total_current_value_paise: number
  total_purchase_price_paise: number
  overall_appreciation_pct: number | null
}

// ── Insurance ────────────────────────────────────────────────────────────────

export type InsurancePolicyOut = {
  id: number
  name: string
  type: string  // health | life | term | vehicle | home | travel | other
  provider: string | null
  policy_number: string | null
  sum_insured_paise: number | null
  premium_paise: number
  premium_frequency: string  // annual | semi_annual | quarterly | monthly
  start_date: string | null
  end_date: string | null
  renewal_date: string | null
  policyholder: string
  covered_members: string | null
  asset_id: number | null
  tax_deduction_section: string | null  // 80C | 80D | 80D_parents
  status: string  // active | lapsed | surrendered | matured
  notes: string | null
  annual_premium_paise: number  // derived
}

export type InsurancePremiumOut = {
  id: number
  policy_id: number
  payment_date: string
  amount_paise: number
  period_start: string | null
  period_end: string | null
  payment_mode: string | null
  reference_number: string | null
  notes: string | null
}

export type InsuranceSummaryOut = {
  active_policy_count: number
  total_annual_premium_paise: number
  renewing_within_60_days: number
  total_80d_self_paise: number
  total_80d_parents_paise: number
  total_80c_paise: number
}

export type JournalEntryOut = {
  entry_date: string
  body: string
  created_at: string
  updated_at: string
}

export type ConstructionProjectOut = {
  id: number
  name: string
}

export type ConstructionSnapshotOut = {
  id: number
  project_id: number
  as_of_date: string
  source_filename: string
  file_sha256: string | null
  parse_warnings: string[]
  row_count: number
}

export type ConstructionProgressRowOut = {
  id: number
  zone_key: string
  zone_type: string
  tower_number: number | null
  section: string
  activity_raw: string
  floors_complete: number | null
  pct_complete: number | null
  status: string | null
  remark: string | null
}

export type ConstructionSnapshotDetailOut = {
  snapshot: ConstructionSnapshotOut
  rows: ConstructionProgressRowOut[]
}

export type ConstructionSeriesPoint = {
  as_of_date: string
  pct_complete: number | null
  floors_complete: number | null
}

export type ConstructionSeriesOut = {
  zone_key: string
  activity_raw: string
  points: ConstructionSeriesPoint[]
}

export type ConstructionUploadResponse = {
  snapshot_id: number
  as_of_date: string
  project_id: number
  parse_warnings: string[]
  zones_parsed: number
  rows_parsed: number
}

export type ConstructionDeleteAllOut = {
  snapshots_deleted: number
  zone_labels_deleted: number
  projects_deleted: number
}

export type TowerDashboardActivityRow = {
  section: string
  activity_raw: string
  pct_reported: number | null
  floors_complete: number | null
  effective_pct: number | null
  floors_pct_of_total: number | null
  status: string | null
}

export type TowerTrendPoint = {
  snapshot_id: number
  as_of_date: string
  avg_effective_pct: number | null
  avg_floors_pct: number | null
  activity_count: number
}

export type ConstructionTowerDashboardOut = {
  zone_key: string
  total_floors: number
  latest_snapshot_id: number | null
  latest_as_of_date: string | null
  latest_snapshot_avg_effective_pct: number | null
  latest_snapshot_avg_floors_pct: number | null
  activity_rows: TowerDashboardActivityRow[]
  trend: TowerTrendPoint[]
}

export type ZoneLabelsOut = {
  labels: Record<string, string>
}
