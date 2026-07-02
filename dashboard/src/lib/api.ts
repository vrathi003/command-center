import type {
  AccountOut,
  AmortizationResponse,
  AssetCostOut,
  AssetDetailOut,
  AssetLoanOut,
  AssetOut,
  AssetPaymentOut,
  AssetSummaryOut,
  BudgetVsActualResponse,
  DashboardAlerts,
  DashboardSummary,
  DebtOut,
  DebtSummaryOut,
  LoanDisbursalOut,
  FixedIncomeOut,
  FixedIncomeSummaryOut,
  FYSummaryReport,
  FYSpendingReport,
  GoalOut,
  HomeInventorySummaryOut,
  HomeItemOut,
  HomeItemServiceEventOut,
  HomeItemSummaryOut,
  IncomeOut,
  IncomeSummaryOut,
  InsurancePolicyOut,
  InsurancePremiumOut,
  InsuranceSummaryOut,
  InvestmentOut,
  JournalEntryOut,
  NetWorthSnapshotOut,
  PortfolioSummaryOut,
  RealEstateOut,
  CreditCardEmiOut,
  CreditCardOut,
  CreditCardStatementApplyResponse,
  ConstructionDeleteAllOut,
  ConstructionProjectOut,
  ConstructionSeriesOut,
  ConstructionSnapshotDetailOut,
  ConstructionSnapshotOut,
  ConstructionTowerDashboardOut,
  ConstructionUploadResponse,
  CreditCardStatementOut,
  SettingsOut,
  SubscriptionOut,
  TransactionDetailOut,
  TransactionImportResult,
  TransactionRow,
  TransactionTemplateOut,
  TransferCreateResponse,
  VehicleOut,
  ZoneLabelsOut,
  StagedEmailTransaction,
  EmailInboxStats,
} from '@/types/api'

function apiBase(): string {
  return import.meta.env.VITE_API_URL?.replace(/\/$/, '') ?? ''
}

async function parseJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function fetchJournalEntry(entryDate: string): Promise<JournalEntryOut | null> {
  const res = await fetch(`${apiBase()}/api/journal/${encodeURIComponent(entryDate)}`)
  if (res.status === 404) {
    return null
  }
  return parseJson<JournalEntryOut>(res)
}

export async function fetchJournalRange(from: string, to: string): Promise<JournalEntryOut[]> {
  const params = new URLSearchParams({ from, to })
  const res = await fetch(`${apiBase()}/api/journal/?${params}`)
  return parseJson<JournalEntryOut[]>(res)
}

export async function putJournalEntry(entryDate: string, body: string): Promise<JournalEntryOut | null> {
  const res = await fetch(`${apiBase()}/api/journal/${encodeURIComponent(entryDate)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  })
  if (res.status === 204) {
    return null
  }
  return parseJson<JournalEntryOut>(res)
}

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const res = await fetch(`${apiBase()}/api/dashboard/summary`)
  return parseJson<DashboardSummary>(res)
}

export async function fetchDashboardAlerts(): Promise<DashboardAlerts> {
  const res = await fetch(`${apiBase()}/api/dashboard/alerts`)
  return parseJson<DashboardAlerts>(res)
}

export async function fetchTransactions(
  limit = 50,
  options?: { startDate?: string; endDate?: string; account?: string },
): Promise<TransactionRow[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (options?.startDate) params.set('start_date', options.startDate)
  if (options?.endDate) params.set('end_date', options.endDate)
  if (options?.account) params.set('account', options.account)
  const res = await fetch(`${apiBase()}/api/transactions/?${params}`)
  return parseJson<TransactionRow[]>(res)
}

export async function fetchTransaction(id: number): Promise<TransactionDetailOut> {
  const res = await fetch(`${apiBase()}/api/transactions/${id}`)
  return parseJson<TransactionDetailOut>(res)
}

export async function putTransaction(
  id: number,
  body: {
    date: string
    amount_paise: number
    category?: string | null
    merchant?: string | null
    payment_mode?: string | null
    transaction_type?: 'debit' | 'credit' | null
    account_id?: number | null
    notes?: string | null
    tags?: string | null
    from_account_id?: number | null
    to_account_id?: number | null
  },
): Promise<{ id: number }> {
  const res = await fetch(`${apiBase()}/api/transactions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<{ id: number }>(res)
}

export async function postManualTransaction(body: {
  date: string
  amount_paise: number
  category: string
  merchant?: string | null
  payment_mode: string
  transaction_type: 'debit' | 'credit'
  account?: string | null
  account_id?: number | null
  notes?: string | null
  tags?: string | null
  source?: string
}): Promise<{ id: number }> {
  const res = await fetch(`${apiBase()}/api/transactions/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<{ id: number }>(res)
}

export async function postTransfer(body: {
  amount_paise: number
  from_account_id: number
  to_account_id: number
  date: string
  notes?: string | null
  tags?: string | null
}): Promise<TransferCreateResponse> {
  const res = await fetch(`${apiBase()}/api/transactions/transfer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<TransferCreateResponse>(res)
}

/** `pdfPassword` unlocks encrypted PDFs or password-protected Excel.
 *  `accountName` tags every row in this upload to a specific account. */
export async function importTransactionsFile(
  file: File,
  options?: { pdfPassword?: string; accountName?: string },
): Promise<TransactionImportResult> {
  const form = new FormData()
  form.append('file', file)
  if (options?.pdfPassword) {
    form.append('pdf_password', options.pdfPassword)
  }
  if (options?.accountName) {
    form.append('account_name', options.accountName)
  }
  const res = await fetch(`${apiBase()}/api/transactions/import`, {
    method: 'POST',
    body: form,
  })
  return parseJson<TransactionImportResult>(res)
}

// --- Transaction templates (quick-add presets) ---

export async function fetchTransactionTemplates(): Promise<TransactionTemplateOut[]> {
  const res = await fetch(`${apiBase()}/api/transaction-templates/`)
  return parseJson<TransactionTemplateOut[]>(res)
}

export async function postTransactionTemplate(body: {
  name: string
  amount: number | null
  merchant: string | null
  category: string | null
  account_id: number | null
  payment_mode: string | null
  transaction_type: 'debit' | 'credit' | 'transfer'
  notes: string | null
  tags: string | null
}): Promise<TransactionTemplateOut> {
  const res = await fetch(`${apiBase()}/api/transaction-templates/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<TransactionTemplateOut>(res)
}

export async function putTransactionTemplate(
  id: number,
  body: {
    name: string
    amount: number | null
    merchant: string | null
    category: string | null
    account_id: number | null
    payment_mode: string | null
    transaction_type: 'debit' | 'credit' | 'transfer'
    notes: string | null
    tags: string | null
  },
): Promise<TransactionTemplateOut> {
  const res = await fetch(`${apiBase()}/api/transaction-templates/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<TransactionTemplateOut>(res)
}

export async function deleteTransactionTemplate(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/transaction-templates/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

// --- Accounts ---

export async function fetchAccounts(activeOnly = false): Promise<AccountOut[]> {
  const q = activeOnly ? '?active_only=true' : ''
  const res = await fetch(`${apiBase()}/api/accounts/${q}`)
  return parseJson<AccountOut[]>(res)
}

export async function fetchAccountTypes(): Promise<string[]> {
  const res = await fetch(`${apiBase()}/api/accounts/types`)
  return parseJson<string[]>(res)
}

export async function postAccount(body: {
  name: string
  type: string
  institution: string | null
  currency: string
}): Promise<AccountOut> {
  const res = await fetch(`${apiBase()}/api/accounts/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AccountOut>(res)
}

export async function putAccount(
  id: number,
  body: {
    name: string
    type: string
    institution: string | null
    currency: string
    is_active: boolean
  },
): Promise<AccountOut> {
  const res = await fetch(`${apiBase()}/api/accounts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AccountOut>(res)
}

export async function deleteAccount(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/accounts/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

/** Must match `TransactionBulkDeleteBody` max_length on the API. */
const BULK_DELETE_TRANSACTIONS_MAX = 200

export async function bulkDeleteTransactions(ids: number[]): Promise<{ deleted: number }> {
  let deleted = 0
  for (let i = 0; i < ids.length; i += BULK_DELETE_TRANSACTIONS_MAX) {
    const chunk = ids.slice(i, i + BULK_DELETE_TRANSACTIONS_MAX)
    const res = await fetch(`${apiBase()}/api/transactions/bulk-delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: chunk }),
    })
    const body = await parseJson<{ deleted: number }>(res)
    deleted += body.deleted
  }
  return { deleted }
}

export async function fetchBudgetVsActual(year: number, month: number): Promise<BudgetVsActualResponse> {
  const q = new URLSearchParams({ year: String(year), month: String(month) })
  const res = await fetch(`${apiBase()}/api/budget/vs-actual?${q}`)
  return parseJson<BudgetVsActualResponse>(res)
}

export async function putBudgetCategory(
  category: string,
  monthly_amount_paise: number,
): Promise<void> {
  const enc = encodeURIComponent(category)
  const res = await fetch(`${apiBase()}/api/budget/category/${enc}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ monthly_amount_paise }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function deleteBudgetCategory(category: string): Promise<void> {
  const enc = encodeURIComponent(category)
  const res = await fetch(`${apiBase()}/api/budget/category/${enc}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function renameBudgetCategory(oldCategory: string, newCategory: string): Promise<void> {
  const res = await fetch(`${apiBase()}/api/budget/rename-category`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      old_category: oldCategory.trim(),
      new_category: newCategory.trim(),
    }),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function postDebt(body: {
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
  tenure_months?: number | null
  first_emi_date?: string | null
  full_emi_start_date?: string | null
}): Promise<DebtOut> {
  const res = await fetch(`${apiBase()}/api/debt/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<DebtOut>(res)
}

export async function putDebt(
  id: number,
  body: {
    name?: string
    lender?: string | null
    type?: string
    original_amount_paise?: number | null
    current_balance_paise?: number
    emi_paise?: number | null
    rate_percent?: number | null
    start_date?: string | null
    next_emi_date?: string | null
    status?: string
    tenure_months?: number | null
    first_emi_date?: string | null
    full_emi_start_date?: string | null
  },
): Promise<DebtOut> {
  const res = await fetch(`${apiBase()}/api/debt/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<DebtOut>(res)
}

export async function deleteDebt(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/debt/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchDebtSummary(): Promise<DebtSummaryOut> {
  const res = await fetch(`${apiBase()}/api/debt/summary`)
  return parseJson<DebtSummaryOut>(res)
}

export async function fetchDebts(): Promise<DebtOut[]> {
  const res = await fetch(`${apiBase()}/api/debt/`)
  return parseJson<DebtOut[]>(res)
}

export async function fetchDebtAmortization(debtId: number): Promise<AmortizationResponse> {
  const res = await fetch(`${apiBase()}/api/debt/${debtId}/amortization`)
  return parseJson<AmortizationResponse>(res)
}

export async function fetchPortfolioSummary(): Promise<PortfolioSummaryOut> {
  const res = await fetch(`${apiBase()}/api/investments/portfolio-summary`)
  return parseJson<PortfolioSummaryOut>(res)
}

export async function fetchInvestments(): Promise<InvestmentOut[]> {
  const res = await fetch(`${apiBase()}/api/investments/`)
  return parseJson<InvestmentOut[]>(res)
}

export async function postInvestment(body: {
  instrument: string
  type: string
  isin_code: string | null
  units: number | null
  avg_price_paise: number | null
  current_price_paise: number | null
  sector?: string | null
  equity_tax_class?: string | null
}): Promise<InvestmentOut> {
  const res = await fetch(`${apiBase()}/api/investments/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<InvestmentOut>(res)
}

export async function putInvestment(
  id: number,
  body: {
    instrument?: string
    type?: string
    isin_code?: string | null
    units?: number | null
    avg_price_paise?: number | null
    current_price_paise?: number | null
    sector?: string | null
    equity_tax_class?: string | null
  },
): Promise<InvestmentOut> {
  const res = await fetch(`${apiBase()}/api/investments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<InvestmentOut>(res)
}

export async function deleteInvestment(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/investments/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchFixedIncomeSummary(): Promise<FixedIncomeSummaryOut> {
  const res = await fetch(`${apiBase()}/api/fixed-income/summary`)
  return parseJson<FixedIncomeSummaryOut>(res)
}

export async function fetchFixedIncome(): Promise<FixedIncomeOut[]> {
  const res = await fetch(`${apiBase()}/api/fixed-income/`)
  return parseJson<FixedIncomeOut[]>(res)
}

export async function postFixedIncome(body: {
  institution: string
  type: string
  principal_paise: number
  rate_percent: number | null
  start_date: string | null
  maturity_date: string | null
}): Promise<FixedIncomeOut> {
  const res = await fetch(`${apiBase()}/api/fixed-income/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<FixedIncomeOut>(res)
}

export async function putFixedIncome(
  id: number,
  body: {
    institution?: string
    type?: string
    principal_paise?: number
    rate_percent?: number | null
    start_date?: string | null
    maturity_date?: string | null
  },
): Promise<FixedIncomeOut> {
  const res = await fetch(`${apiBase()}/api/fixed-income/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<FixedIncomeOut>(res)
}

export async function deleteFixedIncome(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/fixed-income/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchNetWorthHistory(limit = 365): Promise<NetWorthSnapshotOut[]> {
  const res = await fetch(`${apiBase()}/api/net-worth/history?limit=${limit}`)
  return parseJson<NetWorthSnapshotOut[]>(res)
}

export async function postNetWorthSnapshotComputed(): Promise<NetWorthSnapshotOut> {
  const res = await fetch(`${apiBase()}/api/net-worth/snapshot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ computed_from_holdings: true }),
  })
  return parseJson<NetWorthSnapshotOut>(res)
}

export async function fetchGoals(): Promise<GoalOut[]> {
  const res = await fetch(`${apiBase()}/api/goals/`)
  return parseJson<GoalOut[]>(res)
}

export async function postGoal(body: {
  name: string
  category: string | null
  target_amount_paise: number
  current_amount_paise: number
  monthly_contribution_paise: number | null
  target_date: string | null
}): Promise<GoalOut> {
  const res = await fetch(`${apiBase()}/api/goals/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<GoalOut>(res)
}

export async function putGoal(
  id: number,
  body: {
    name: string
    category: string | null
    target_amount_paise: number
    current_amount_paise: number
    monthly_contribution_paise: number | null
    target_date: string | null
  },
): Promise<GoalOut> {
  const res = await fetch(`${apiBase()}/api/goals/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<GoalOut>(res)
}

export async function deleteGoal(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/goals/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchHomeInventorySummary(): Promise<HomeInventorySummaryOut> {
  const res = await fetch(`${apiBase()}/api/home-items/summary`)
  return parseJson<HomeInventorySummaryOut>(res)
}

export async function fetchHomeItems(params?: {
  category?: string
  room?: string
}): Promise<HomeItemSummaryOut[]> {
  const q = new URLSearchParams()
  if (params?.category) q.set('category', params.category)
  if (params?.room) q.set('room', params.room)
  const qs = q.toString()
  const res = await fetch(`${apiBase()}/api/home-items${qs ? `?${qs}` : '/'}`)
  return parseJson<HomeItemSummaryOut[]>(res)
}

export async function fetchHomeItem(id: number): Promise<HomeItemOut> {
  const res = await fetch(`${apiBase()}/api/home-items/${id}`)
  return parseJson<HomeItemOut>(res)
}

export async function postHomeItem(body: {
  name: string
  category: string
  brand?: string | null
  model?: string | null
  serial_number?: string | null
  room_location?: string | null
  purchase_date?: string | null
  purchase_price_paise?: number | null
  retailer?: string | null
  warranty_end_date?: string | null
  extended_warranty?: boolean
  condition_status?: string
  notes?: string | null
}): Promise<HomeItemOut> {
  const res = await fetch(`${apiBase()}/api/home-items/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<HomeItemOut>(res)
}

export async function putHomeItem(
  id: number,
  body: {
    name: string
    category: string
    brand?: string | null
    model?: string | null
    serial_number?: string | null
    room_location?: string | null
    purchase_date?: string | null
    purchase_price_paise?: number | null
    retailer?: string | null
    warranty_end_date?: string | null
    extended_warranty?: boolean
    condition_status?: string
    notes?: string | null
  },
): Promise<HomeItemOut> {
  const res = await fetch(`${apiBase()}/api/home-items/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<HomeItemOut>(res)
}

export async function deleteHomeItem(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/home-items/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchHomeItemServiceEvents(itemId: number): Promise<HomeItemServiceEventOut[]> {
  const res = await fetch(`${apiBase()}/api/home-items/${itemId}/service-events`)
  return parseJson<HomeItemServiceEventOut[]>(res)
}

export async function postHomeItemServiceEvent(
  itemId: number,
  body: {
    service_date: string
    event_type: string
    vendor?: string | null
    description?: string | null
    cost_paise?: number | null
    next_service_due?: string | null
    notes?: string | null
  },
): Promise<HomeItemServiceEventOut> {
  const res = await fetch(`${apiBase()}/api/home-items/${itemId}/service-events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<HomeItemServiceEventOut>(res)
}

export async function putHomeItemServiceEvent(
  itemId: number,
  eventId: number,
  body: {
    service_date: string
    event_type: string
    vendor?: string | null
    description?: string | null
    cost_paise?: number | null
    next_service_due?: string | null
    notes?: string | null
  },
): Promise<HomeItemServiceEventOut> {
  const res = await fetch(`${apiBase()}/api/home-items/${itemId}/service-events/${eventId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<HomeItemServiceEventOut>(res)
}

export async function deleteHomeItemServiceEvent(itemId: number, eventId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/home-items/${itemId}/service-events/${eventId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchIncomeSummary(): Promise<IncomeSummaryOut> {
  const res = await fetch(`${apiBase()}/api/income/summary`)
  return parseJson<IncomeSummaryOut>(res)
}

export async function fetchIncomeStreams(includeInactive = false): Promise<IncomeOut[]> {
  const base = `${apiBase()}/api/income/`
  const res = await fetch(includeInactive ? `${base}?include_inactive=true` : base)
  return parseJson<IncomeOut[]>(res)
}

export async function postIncomeStream(body: {
  name: string
  type: string
  amount_paise: number | null
  frequency: string
  taxability: string
  is_active?: boolean
}): Promise<IncomeOut> {
  const res = await fetch(`${apiBase()}/api/income/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<IncomeOut>(res)
}

export async function putIncomeStream(
  id: number,
  body: {
    name: string
    type: string
    amount_paise: number | null
    frequency: string
    taxability: string
    is_active: boolean
  },
): Promise<IncomeOut> {
  const res = await fetch(`${apiBase()}/api/income/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<IncomeOut>(res)
}

export async function deleteIncomeStream(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/income/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchSettings(): Promise<SettingsOut> {
  const res = await fetch(`${apiBase()}/api/settings/`)
  return parseJson<SettingsOut>(res)
}

export async function putSettings(body: {
  current_fy?: string
  tax_regime?: string | null
  tax_80c_annual_paise?: number | null
  tax_80d_annual_paise?: number | null
}): Promise<SettingsOut> {
  const res = await fetch(`${apiBase()}/api/settings/`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<SettingsOut>(res)
}

export async function fetchFYSpending(fy?: string): Promise<FYSpendingReport> {
  const q = fy ? `?fy=${encodeURIComponent(fy)}` : ''
  const res = await fetch(`${apiBase()}/api/reports/fy-spending${q}`)
  return parseJson<FYSpendingReport>(res)
}

export async function fetchFYSummary(fy?: string): Promise<FYSummaryReport> {
  const q = fy ? `?fy=${encodeURIComponent(fy)}` : ''
  const res = await fetch(`${apiBase()}/api/reports/fy-summary${q}`)
  return parseJson<FYSummaryReport>(res)
}

export async function fetchCreditCards(activeOnly = false): Promise<CreditCardOut[]> {
  const q = activeOnly ? '?active_only=true' : ''
  const res = await fetch(`${apiBase()}/api/credit-cards/${q}`)
  return parseJson<CreditCardOut[]>(res)
}

export async function fetchCreditCard(id: number): Promise<CreditCardOut> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${id}`)
  return parseJson<CreditCardOut>(res)
}

export async function postCreditCard(body: {
  name: string
  issuer: string | null
  last_four: string | null
  credit_limit_paise: number
  current_balance_paise: number | null
  notes: string | null
  is_active: boolean
}): Promise<CreditCardOut> {
  const res = await fetch(`${apiBase()}/api/credit-cards/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<CreditCardOut>(res)
}

export async function putCreditCard(
  id: number,
  body: {
    name?: string
    issuer?: string | null
    last_four?: string | null
    credit_limit_paise?: number
    current_balance_paise?: number | null
    notes?: string | null
    is_active?: boolean
  },
): Promise<CreditCardOut> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<CreditCardOut>(res)
}

export async function deleteCreditCard(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchCreditCardEmis(cardId: number): Promise<CreditCardEmiOut[]> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/emis`)
  return parseJson<CreditCardEmiOut[]>(res)
}

export async function postCreditCardEmi(
  cardId: number,
  body: {
    description: string
    limit_blocked_paise: number
    emi_amount_paise: number
    tenure_months: number
    installments_paid: number
    is_active: boolean
    notes: string | null
    loan_type?: string | null
    creation_date?: string | null
    finish_date?: string | null
    principal_paise?: number | null
    outstanding_instalment_paise?: number | null
  },
): Promise<CreditCardEmiOut> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/emis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<CreditCardEmiOut>(res)
}

export async function putCreditCardEmi(
  cardId: number,
  emiId: number,
  body: {
    description?: string
    limit_blocked_paise?: number
    emi_amount_paise?: number
    tenure_months?: number
    installments_paid?: number
    is_active?: boolean
    notes?: string | null
    loan_type?: string | null
    creation_date?: string | null
    finish_date?: string | null
    principal_paise?: number | null
    outstanding_instalment_paise?: number | null
  },
): Promise<CreditCardEmiOut> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/emis/${emiId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<CreditCardEmiOut>(res)
}

export async function deleteCreditCardEmi(cardId: number, emiId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/emis/${emiId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchCreditCardStatements(cardId: number): Promise<CreditCardStatementOut[]> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/statements`)
  return parseJson<CreditCardStatementOut[]>(res)
}

export async function fetchCreditCardStatement(
  cardId: number,
  statementId: number,
): Promise<CreditCardStatementOut> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/statements/${statementId}`)
  return parseJson<CreditCardStatementOut>(res)
}

export async function uploadCreditCardStatement(
  cardId: number,
  file: File,
  pdfPassword?: string,
): Promise<CreditCardStatementOut> {
  const form = new FormData()
  form.append('file', file)
  if (pdfPassword) {
    form.append('pdf_password', pdfPassword)
  }
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/statements`, {
    method: 'POST',
    body: form,
  })
  return parseJson<CreditCardStatementOut>(res)
}

export async function applyCreditCardStatement(
  cardId: number,
  statementId: number,
): Promise<CreditCardStatementApplyResponse> {
  const res = await fetch(
    `${apiBase()}/api/credit-cards/${cardId}/statements/${statementId}/apply`,
    { method: 'POST' },
  )
  return parseJson<CreditCardStatementApplyResponse>(res)
}

export async function deleteCreditCardStatement(cardId: number, statementId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/credit-cards/${cardId}/statements/${statementId}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchSubscriptions(activeOnly = false): Promise<SubscriptionOut[]> {
  const q = activeOnly ? '?active_only=true' : ''
  const res = await fetch(`${apiBase()}/api/subscriptions/${q}`)
  return parseJson<SubscriptionOut[]>(res)
}

export async function postSubscription(body: {
  name: string
  provider: string | null
  category: string | null
  amount_paise: number
  billing_cycle: string
  next_billing_date: string | null
  notes: string | null
  is_active: boolean
}): Promise<SubscriptionOut> {
  const res = await fetch(`${apiBase()}/api/subscriptions/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<SubscriptionOut>(res)
}

export async function putSubscription(
  id: number,
  body: {
    name?: string
    provider?: string | null
    category?: string | null
    amount_paise?: number
    billing_cycle?: string
    next_billing_date?: string | null
    notes?: string | null
    is_active?: boolean
  },
): Promise<SubscriptionOut> {
  const res = await fetch(`${apiBase()}/api/subscriptions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<SubscriptionOut>(res)
}

export async function deleteSubscription(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/subscriptions/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

// ── Loan disbursals ──────────────────────────────────────────────────────────

export async function fetchDisbursals(debtId: number): Promise<LoanDisbursalOut[]> {
  const res = await fetch(`${apiBase()}/api/debt/${debtId}/disbursals`)
  return parseJson<LoanDisbursalOut[]>(res)
}

export async function postDisbursal(
  debtId: number,
  body: { disbursal_date: string; amount_paise: number; notes?: string | null },
): Promise<LoanDisbursalOut> {
  const res = await fetch(`${apiBase()}/api/debt/${debtId}/disbursals`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<LoanDisbursalOut>(res)
}

export async function deleteDisbursal(debtId: number, disbursalId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/debt/${debtId}/disbursals/${disbursalId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function syncDebtBalance(debtId: number): Promise<DebtOut> {
  const res = await fetch(`${apiBase()}/api/debt/${debtId}/sync-balance`, { method: 'POST' })
  return parseJson<DebtOut>(res)
}

export async function syncAllDebtBalances(): Promise<DebtOut[]> {
  const res = await fetch(`${apiBase()}/api/debt/sync-all-balances`, { method: 'POST' })
  return parseJson<DebtOut[]>(res)
}

export async function downloadFYSummaryPdf(fy?: string): Promise<void> {
  const q = fy ? `?fy=${encodeURIComponent(fy)}` : ''
  const res = await fetch(`${apiBase()}/api/reports/fy-summary.pdf${q}`)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  try {
    const a = document.createElement('a')
    a.href = url
    a.download = `fy-${(fy ?? 'summary').replace(/\//g, '-')}-report.pdf`
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

// ── Assets ────────────────────────────────────────────────────────────────────

export async function fetchAssets(): Promise<AssetOut[]> {
  const res = await fetch(`${apiBase()}/api/assets/`)
  return parseJson<AssetOut[]>(res)
}

export async function fetchAssetSummary(): Promise<AssetSummaryOut> {
  const res = await fetch(`${apiBase()}/api/assets/summary`)
  return parseJson<AssetSummaryOut>(res)
}

export async function fetchAssetDetail(id: number): Promise<AssetDetailOut> {
  const res = await fetch(`${apiBase()}/api/assets/${id}`)
  return parseJson<AssetDetailOut>(res)
}

export async function postAsset(body: Partial<AssetOut>): Promise<AssetOut> {
  const res = await fetch(`${apiBase()}/api/assets/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AssetOut>(res)
}

export async function putAsset(id: number, body: Partial<AssetOut>): Promise<AssetOut> {
  const res = await fetch(`${apiBase()}/api/assets/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AssetOut>(res)
}

export async function deleteAsset(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/assets/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function putRealEstate(assetId: number, body: Partial<RealEstateOut>): Promise<RealEstateOut> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/real-estate`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<RealEstateOut>(res)
}

export async function putVehicle(assetId: number, body: Partial<VehicleOut>): Promise<VehicleOut> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/vehicle`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<VehicleOut>(res)
}

export async function postAssetCost(
  assetId: number,
  body: { cost_type: string; amount_paise: number; paid_date?: string | null; description?: string | null; is_paid?: boolean },
): Promise<AssetCostOut> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/costs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AssetCostOut>(res)
}

export async function putAssetCost(
  assetId: number,
  costId: number,
  body: { cost_type: string; amount_paise: number; paid_date?: string | null; description?: string | null; is_paid?: boolean },
): Promise<AssetCostOut> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/costs/${costId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AssetCostOut>(res)
}

export async function deleteAssetCost(assetId: number, costId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/costs/${costId}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function postAssetLoan(
  assetId: number,
  body: {
    debt_id: number
    sanctioned_amount_paise?: number | null
    disbursed_amount_paise?: number | null
    pre_emi_paise?: number | null
    final_emi_paise?: number | null
    notes?: string | null
  },
): Promise<AssetLoanOut> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/loans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AssetLoanOut>(res)
}

export async function deleteAssetLoan(assetId: number, loanId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/loans/${loanId}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export type AssetPaymentBody = {
  milestone?: string | null
  amount_cash_paise?: number
  amount_loan_paise?: number
  /** Legacy: used when cash and loan are both zero. */
  amount_paise?: number | null
  payment_date?: string | null
  reference_number?: string | null
  notes?: string | null
  is_paid?: boolean
  due_date?: string | null
  paid_date?: string | null
  fund_source?: 'cash' | 'bank_loan'
}

export async function postAssetPayment(
  assetId: number,
  body: AssetPaymentBody,
): Promise<AssetPaymentOut> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/payments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AssetPaymentOut>(res)
}

export async function putAssetPayment(
  assetId: number,
  paymentId: number,
  body: AssetPaymentBody,
): Promise<AssetPaymentOut> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/payments/${paymentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<AssetPaymentOut>(res)
}

export async function deleteAssetPayment(assetId: number, paymentId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/assets/${assetId}/payments/${paymentId}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

// ── Insurance ────────────────────────────────────────────────────────────────

export async function fetchInsurancePolicies(): Promise<InsurancePolicyOut[]> {
  const res = await fetch(`${apiBase()}/api/insurance/`)
  return parseJson<InsurancePolicyOut[]>(res)
}

export async function fetchInsuranceSummary(): Promise<InsuranceSummaryOut> {
  const res = await fetch(`${apiBase()}/api/insurance/summary`)
  return parseJson<InsuranceSummaryOut>(res)
}

export async function postInsurancePolicy(body: Record<string, unknown>): Promise<InsurancePolicyOut> {
  const res = await fetch(`${apiBase()}/api/insurance/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<InsurancePolicyOut>(res)
}

export async function putInsurancePolicy(id: number, body: Record<string, unknown>): Promise<InsurancePolicyOut> {
  const res = await fetch(`${apiBase()}/api/insurance/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<InsurancePolicyOut>(res)
}

export async function deleteInsurancePolicy(id: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/insurance/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchInsurancePremiums(policyId: number): Promise<InsurancePremiumOut[]> {
  const res = await fetch(`${apiBase()}/api/insurance/${policyId}/premiums`)
  return parseJson<InsurancePremiumOut[]>(res)
}

export async function postInsurancePremium(
  policyId: number,
  body: {
    payment_date: string
    amount_paise: number
    period_start?: string | null
    period_end?: string | null
    payment_mode?: string | null
    reference_number?: string | null
    notes?: string | null
  },
): Promise<InsurancePremiumOut> {
  const res = await fetch(`${apiBase()}/api/insurance/${policyId}/premiums`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return parseJson<InsurancePremiumOut>(res)
}

export async function deleteInsurancePremium(policyId: number, premiumId: number): Promise<void> {
  const res = await fetch(`${apiBase()}/api/insurance/${policyId}/premiums/${premiumId}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
}

export async function fetchConstructionProjects(): Promise<ConstructionProjectOut[]> {
  const res = await fetch(`${apiBase()}/api/construction/projects`)
  return parseJson<ConstructionProjectOut[]>(res)
}

export async function uploadConstructionPdf(file: File): Promise<ConstructionUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${apiBase()}/api/construction/upload`, {
    method: 'POST',
    body: form,
  })
  return parseJson<ConstructionUploadResponse>(res)
}

export async function fetchConstructionSnapshots(projectId?: number): Promise<ConstructionSnapshotOut[]> {
  const q = projectId != null ? `?project_id=${projectId}` : ''
  const res = await fetch(`${apiBase()}/api/construction/snapshots${q}`)
  return parseJson<ConstructionSnapshotOut[]>(res)
}

export async function fetchConstructionSnapshotDetail(
  snapshotId: number,
): Promise<ConstructionSnapshotDetailOut> {
  const res = await fetch(`${apiBase()}/api/construction/snapshots/${snapshotId}`)
  return parseJson<ConstructionSnapshotDetailOut>(res)
}

export async function fetchConstructionSeries(
  zoneKey: string,
  activityRaw: string,
  projectId?: number,
): Promise<ConstructionSeriesOut> {
  const params = new URLSearchParams({ zone_key: zoneKey, activity_raw: activityRaw })
  if (projectId != null) params.set('project_id', String(projectId))
  const res = await fetch(`${apiBase()}/api/construction/series?${params}`)
  return parseJson<ConstructionSeriesOut>(res)
}

export async function fetchConstructionTowerDashboard(
  zoneKey: string,
  options?: { projectId?: number; totalFloors?: number },
): Promise<ConstructionTowerDashboardOut> {
  const params = new URLSearchParams({ zone_key: zoneKey })
  if (options?.projectId != null) params.set('project_id', String(options.projectId))
  if (options?.totalFloors != null) params.set('total_floors', String(options.totalFloors))
  const res = await fetch(`${apiBase()}/api/construction/tower-dashboard?${params}`)
  return parseJson<ConstructionTowerDashboardOut>(res)
}

export async function fetchConstructionZones(projectId?: number): Promise<string[]> {
  const q = projectId != null ? `?project_id=${projectId}` : ''
  const res = await fetch(`${apiBase()}/api/construction/zones${q}`)
  return parseJson<string[]>(res)
}

export async function fetchConstructionZoneActivities(
  zoneKey: string,
  projectId?: number,
): Promise<string[]> {
  const params = new URLSearchParams()
  if (projectId != null) params.set('project_id', String(projectId))
  const q = params.toString()
  const res = await fetch(
    `${apiBase()}/api/construction/zones/${encodeURIComponent(zoneKey)}/activities${q ? `?${q}` : ''}`,
  )
  return parseJson<string[]>(res)
}

export async function fetchConstructionZoneLabels(projectId?: number): Promise<ZoneLabelsOut> {
  const q = projectId != null ? `?project_id=${projectId}` : ''
  const res = await fetch(`${apiBase()}/api/construction/zone-labels${q}`)
  return parseJson<ZoneLabelsOut>(res)
}

export async function putConstructionZoneLabels(
  labels: Array<{ zone_key: string; label: string }>,
  projectId?: number,
): Promise<ZoneLabelsOut> {
  const q = projectId != null ? `?project_id=${projectId}` : ''
  const res = await fetch(`${apiBase()}/api/construction/zone-labels${q}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ labels }),
  })
  return parseJson<ZoneLabelsOut>(res)
}

export async function deleteConstructionAllData(): Promise<ConstructionDeleteAllOut> {
  const res = await fetch(`${apiBase()}/api/construction/all-data`, { method: 'DELETE' })
  return parseJson<ConstructionDeleteAllOut>(res)
}

// ── Email Inbox ───────────────────────────────────────────────────────────────

export async function fetchEmailInboxStats(): Promise<EmailInboxStats> {
  const res = await fetch(`${apiBase()}/api/email-inbox/stats`)
  return parseJson<EmailInboxStats>(res)
}

export async function fetchEmailInbox(status?: string): Promise<StagedEmailTransaction[]> {
  const url = status
    ? `${apiBase()}/api/email-inbox/?status=${encodeURIComponent(status)}`
    : `${apiBase()}/api/email-inbox/`
  const res = await fetch(url)
  return parseJson<StagedEmailTransaction[]>(res)
}

export async function syncGmailNow(): Promise<{ new_items: number }> {
  const res = await fetch(`${apiBase()}/api/email-inbox/sync`, { method: 'POST' })
  return parseJson<{ new_items: number }>(res)
}

export async function updateStagedEmail(
  id: number,
  fields: {
    parsed_date?: string | null
    parsed_amount_paise?: number | null
    parsed_merchant?: string | null
    parsed_category?: string | null
    parsed_payment_mode?: string | null
    parsed_transaction_type?: string | null
    suggested_account_id?: number | null
  },
): Promise<StagedEmailTransaction> {
  const res = await fetch(`${apiBase()}/api/email-inbox/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  return parseJson<StagedEmailTransaction>(res)
}

export async function approveEmailTransaction(
  id: number,
  overrides?: {
    parsed_date?: string | null
    parsed_amount_paise?: number | null
    parsed_merchant?: string | null
    parsed_category?: string | null
    parsed_payment_mode?: string | null
    parsed_transaction_type?: string | null
    account_id?: number | null
    notes?: string | null
  },
): Promise<StagedEmailTransaction> {
  const res = await fetch(`${apiBase()}/api/email-inbox/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(overrides ?? {}),
  })
  return parseJson<StagedEmailTransaction>(res)
}

export async function rejectEmailTransaction(id: number): Promise<StagedEmailTransaction> {
  const res = await fetch(`${apiBase()}/api/email-inbox/${id}/reject`, { method: 'POST' })
  return parseJson<StagedEmailTransaction>(res)
}

export async function clearRejectedEmails(): Promise<{ deleted: number }> {
  const res = await fetch(`${apiBase()}/api/email-inbox/rejected`, { method: 'DELETE' })
  return parseJson<{ deleted: number }>(res)
}
