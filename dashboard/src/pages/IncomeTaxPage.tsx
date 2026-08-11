import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { INCOME_FREQUENCIES, INCOME_TYPES, TAXABILITY } from '@/constants/income'
import {
  deleteIncomeStream,
  fetchAccounts,
  fetchIncomeStreams,
  fetchIncomeSummary,
  fetchSettings,
  postIncomeStream,
  putIncomeStream,
  putSettings,
  recordIncome,
} from '@/lib/api'
import { estimateNewRegimeTaxPaise, estimateOldRegimeTaxPaise } from '@/lib/indiaTax'
import { formatPaise, formatPaiseCompact } from '@/lib/format'
import type { AccountOut, IncomeOut, RecordIncomeOut } from '@/types/api'

const BANK_ACCOUNT_TYPES = new Set(['savings', 'current', 'wallet'])

function filterBankAccounts(accounts: AccountOut[]): AccountOut[] {
  return accounts.filter((a) => BANK_ACCOUNT_TYPES.has(a.type))
}


function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) {
    return null
  }
  return Math.round(n * 100)
}

export function IncomeTaxPage() {
  const qc = useQueryClient()

  const summary = useQuery({
    queryKey: ['income-summary'],
    queryFn: fetchIncomeSummary,
  })

  const streams = useQuery({
    queryKey: ['income-streams'],
    queryFn: () => fetchIncomeStreams(true),
  })

  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: () => fetchAccounts(true),
  })

  const bankAccounts = useMemo(
    () => filterBankAccounts(accounts.data ?? []),
    [accounts.data],
  )

  const [recordIncomeId, setRecordIncomeId] = useState<number | null>(null)

  const taxSettings = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const [regimeDraft, setRegimeDraft] = useState<'old' | 'new' | '' | null>(null)
  const [c80Draft, setC80Draft] = useState<string | null>(null)
  const [d80Draft, setD80Draft] = useState<string | null>(null)

  const regime = useMemo((): 'old' | 'new' | '' => {
    if (regimeDraft !== null) {
      return regimeDraft
    }
    const r = taxSettings.data?.tax_regime
    return r === 'old' || r === 'new' ? r : ''
  }, [regimeDraft, taxSettings.data?.tax_regime])

  const c80 = useMemo(() => {
    if (c80Draft !== null) {
      return c80Draft
    }
    const p = taxSettings.data?.tax_80c_annual_paise
    return p != null ? String(p / 100) : ''
  }, [c80Draft, taxSettings.data?.tax_80c_annual_paise])

  const d80 = useMemo(() => {
    if (d80Draft !== null) {
      return d80Draft
    }
    const p = taxSettings.data?.tax_80d_annual_paise
    return p != null ? String(p / 100) : ''
  }, [d80Draft, taxSettings.data?.tax_80d_annual_paise])

  const saveTax = useMutation({
    mutationFn: () =>
      putSettings({
        tax_regime: regime === '' ? '' : regime,
        tax_80c_annual_paise: c80.trim() === '' ? 0 : (rupeesToPaise(c80) ?? 0),
        tax_80d_annual_paise: d80.trim() === '' ? 0 : (rupeesToPaise(d80) ?? 0),
      }),
    onSuccess: () => {
      setRegimeDraft(null)
      setC80Draft(null)
      setD80Draft(null)
      void qc.invalidateQueries({ queryKey: ['settings'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const taxCompare = useMemo(() => {
    const monthly = summary.data?.total_monthly_equivalent_paise ?? 0
    const annualGrossPaise = monthly * 12
    const tax80cPaise = c80.trim() === '' ? 0 : (rupeesToPaise(c80) ?? 0)
    const tax80dPaise = d80.trim() === '' ? 0 : (rupeesToPaise(d80) ?? 0)
    const base = { annualGrossPaise, tax80cPaise, tax80dPaise }
    return {
      old: estimateOldRegimeTaxPaise(base),
      new: estimateNewRegimeTaxPaise(base),
    }
  }, [summary.data?.total_monthly_equivalent_paise, c80, d80])

  const [nName, setNName] = useState('Salary — primary')
  const [nType, setNType] = useState<string>(INCOME_TYPES[0])
  const [nAmt, setNAmt] = useState('150000')
  const [nFreq, setNFreq] = useState<string>(INCOME_FREQUENCIES[0])
  const [nTax, setNTax] = useState<string>(TAXABILITY[0])
  const [nDefaultAccount, setNDefaultAccount] = useState('')
  const [nCategory, setNCategory] = useState('Salary')

  const add = useMutation({
    mutationFn: postIncomeStream,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['income-streams'] })
      void qc.invalidateQueries({ queryKey: ['income-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const update = useMutation({
    mutationFn: (args: {
      id: number
      name: string
      type: string
      amount_paise: number | null
      frequency: string
      taxability: string
      is_active: boolean
      default_account_id?: number | null
      category?: string | null
    }) => {
      const { id, ...body } = args
      return putIncomeStream(id, body)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['income-streams'] })
      void qc.invalidateQueries({ queryKey: ['income-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const remove = useMutation({
    mutationFn: deleteIncomeStream,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['income-streams'] })
      void qc.invalidateQueries({ queryKey: ['income-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  if (summary.isPending || streams.isPending || taxSettings.isPending || accounts.isPending) {
    return <PageLoading lines={4} showFooterBlock />
  }

  if (summary.isError || streams.isError || taxSettings.isError || accounts.isError) {
    return (
      <PageError
        title="Could not load income data"
        message={
          <p className="text-sm">
            {String(summary.error ?? streams.error ?? taxSettings.error ?? accounts.error)}
          </p>
        }
      />
    )
  }

  const s = summary.data
  const list = streams.data

  const recordIncomeStream = recordIncomeId != null
    ? list.find((row) => row.id === recordIncomeId) ?? null
    : null

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Income"
        title="Income & tax"
        description="Multiple income streams for tax planning · Record income posts to the ledger and drives savings rate"
      />

      <section className="grid gap-4 sm:grid-cols-2">
        <KpiCard tone="neutral" label="Active streams" value={String(s.stream_count)} />
        <KpiCard
          tone="spending"
          label="Monthly run-rate (est.)"
          value={formatPaiseCompact(s.total_monthly_equivalent_paise)}
        />
      </section>

      <section>
        <SectionTitle>Tax profile (India)</SectionTitle>
        <Panel>
        <h2 className="sr-only">Tax profile (India)</h2>
        <p className="mb-3 text-xs text-zinc-500">
          Used for your own planning labels only. Set financial year under Settings.
        </p>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Regime
            <select
              className="mt-1 rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-900"
              value={regime}
              onChange={(e) => setRegimeDraft(e.target.value as 'old' | 'new' | '')}
            >
              <option value="">Not set</option>
              <option value="old">Old (with deductions)</option>
              <option value="new">New (lower rates)</option>
            </select>
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            80C / deductions bucket (₹ / year)
            <input
              className="mt-1 w-36 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={c80}
              onChange={(e) => setC80Draft(e.target.value)}
              placeholder="e.g. 150000"
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            80D health insurance (₹ / year)
            <input
              className="mt-1 w-36 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={d80}
              onChange={(e) => setD80Draft(e.target.value)}
              placeholder="e.g. 25000"
            />
          </label>
          <button
            type="button"
            disabled={saveTax.isPending}
            onClick={() => saveTax.mutate()}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            Save tax profile
          </button>
        </div>
        {saveTax.isError ? <p className="mt-2 text-sm text-red-700">{String(saveTax.error)}</p> : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Old vs new regime (illustrative)</SectionTitle>
        <Panel>
        <h2 className="sr-only">Old vs new regime (illustrative)</h2>
        <p className="mb-3 text-xs text-zinc-500">
          Uses your active income run-rate × 12 as annual gross, minus simplified standard deductions
          and 80C/80D caps in the model. Does not include surcharge, rebate 87A, or HRA — for planning
          only.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3">
            <p className="text-xs font-medium text-zinc-500">Old regime (est. tax)</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-zinc-900">
              {formatPaise(taxCompare.old)}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3">
            <p className="text-xs font-medium text-zinc-500">New regime (est. tax)</p>
            <p className="mt-1 text-lg font-semibold tabular-nums text-zinc-900">
              {formatPaise(taxCompare.new)}
            </p>
          </div>
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Lower estimate is not necessarily better — old regime benefits from 80C/80D; new regime uses
          higher standard deduction and different slabs.
        </p>
        </Panel>
      </section>

      <section>
        <SectionTitle>Add income stream</SectionTitle>
        <Panel>
        <h2 className="sr-only">Add income stream</h2>
        <form
          className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end"
          onSubmit={(e) => {
            e.preventDefault()
            const p = rupeesToPaise(nAmt)
            if (p == null) {
              return
            }
            add.mutate({
              name: nName.trim() || 'Income',
              type: nType,
              amount_paise: p,
              frequency: nFreq,
              taxability: nTax,
              is_active: true,
              default_account_id:
                nDefaultAccount.trim() === ''
                  ? null
                  : Number.parseInt(nDefaultAccount, 10) || null,
              category: nCategory.trim() || null,
            })
          }}
        >
          <label className="text-xs font-medium text-zinc-600">
            Name
            <input
              className="mt-1 block w-48 rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
              value={nName}
              onChange={(e) => setNName(e.target.value)}
            />
          </label>
          <label className="text-xs font-medium text-zinc-600">
            Type
            <select
              className="mt-1 block rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
              value={nType}
              onChange={(e) => setNType(e.target.value)}
            >
              {INCOME_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-zinc-600">
            Amount (₹ per period)
            <input
              className="mt-1 block w-32 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={nAmt}
              onChange={(e) => setNAmt(e.target.value)}
            />
          </label>
          <label className="text-xs font-medium text-zinc-600">
            Frequency
            <select
              className="mt-1 block rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
              value={nFreq}
              onChange={(e) => setNFreq(e.target.value)}
            >
              {INCOME_FREQUENCIES.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-zinc-600">
            Taxability
            <select
              className="mt-1 block rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
              value={nTax}
              onChange={(e) => setNTax(e.target.value)}
            >
              {TAXABILITY.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-zinc-600">
            Default bank
            <select
              className="mt-1 block rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
              value={nDefaultAccount}
              onChange={(e) => setNDefaultAccount(e.target.value)}
            >
              <option value="">— none —</option>
              {bankAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}{a.institution ? ` · ${a.institution}` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-zinc-600">
            Category
            <input
              className="mt-1 block w-28 rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
              value={nCategory}
              onChange={(e) => setNCategory(e.target.value)}
              placeholder="Salary"
            />
          </label>
          <button
            type="submit"
            disabled={add.isPending}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            Add stream
          </button>
        </form>
        {add.isError ? <p className="mt-2 text-sm text-red-700">{String(add.error)}</p> : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Income streams</SectionTitle>
        <Panel variant="table" padding={false}>
        <table className="w-full min-w-[1100px] text-left text-sm">
          <thead className="bg-zinc-50 text-xs font-medium uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Type</th>
              <th className="px-4 py-2 text-right">Amount</th>
              <th className="px-4 py-2">Frequency</th>
              <th className="px-4 py-2">Tax</th>
              <th className="px-4 py-2">Bank</th>
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2 text-right">Monthly eq.</th>
              <th className="px-4 py-2">Active</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {list.map((row) => (
              <IncomeRow
                key={row.id}
                row={row}
                bankAccounts={bankAccounts}
                onSave={(body) => update.mutate({ id: row.id, ...body })}
                onDelete={() => remove.mutate(row.id)}
                onRecordIncome={() => setRecordIncomeId(row.id)}
                busy={update.isPending || remove.isPending}
              />
            ))}
          </tbody>
        </table>
        {list.length === 0 ? (
          <p className="p-6 text-center text-sm text-zinc-500">No income streams — add your first above.</p>
        ) : null}
        </Panel>
      </section>

      {recordIncomeStream ? (
        <RecordIncomeModal
          stream={recordIncomeStream}
          bankAccounts={bankAccounts}
          onClose={() => setRecordIncomeId(null)}
          onSuccess={() => {
            void qc.invalidateQueries({ queryKey: ['income-streams'] })
            void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
          }}
        />
      ) : null}
    </div>
  )
}

function RecordIncomeModal({
  stream,
  bankAccounts,
  onClose,
  onSuccess,
}: {
  stream: IncomeOut
  bankAccounts: AccountOut[]
  onClose: () => void
  onSuccess: () => void
}) {
  const today = new Date().toISOString().slice(0, 10)
  const [date, setDate] = useState(today)
  const [accountId, setAccountId] = useState(
    stream.default_account_id != null ? String(stream.default_account_id) : '',
  )
  const [amountOverride, setAmountOverride] = useState('')
  const [category, setCategory] = useState(stream.category ?? 'Salary')
  const [rememberAccount, setRememberAccount] = useState(false)

  const record = useMutation({
    mutationFn: async (): Promise<RecordIncomeOut> => {
      const body: {
        date: string
        amount_paise?: number
        account_id?: number
        category?: string
      } = { date: date.trim() }
      const acctId = Number.parseInt(accountId, 10)
      if (!Number.isNaN(acctId) && acctId > 0) body.account_id = acctId
      if (amountOverride.trim() !== '') {
        const paise = rupeesToPaise(amountOverride)
        if (paise == null || paise <= 0) throw new Error('Invalid amount')
        body.amount_paise = paise
      }
      if (category.trim() !== '') body.category = category.trim()
      const result = await recordIncome(stream.id, body)
      if (
        rememberAccount
        && !Number.isNaN(acctId)
        && acctId > 0
        && acctId !== stream.default_account_id
      ) {
        await putIncomeStream(stream.id, {
          name: stream.name,
          type: stream.type,
          amount_paise: stream.amount_paise,
          frequency: stream.frequency,
          taxability: stream.taxability,
          is_active: stream.is_active,
          default_account_id: acctId,
          category: category.trim() || stream.category,
        })
      }
      return result
    },
    onSuccess: () => onSuccess(),
  })

  const inputCls = 'mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm'
  const inputNumCls = `${inputCls} text-right tabular-nums`

  const canSubmit =
    date.trim() !== ''
    && (accountId !== '' || stream.default_account_id != null)
    && !record.isPending

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal
      onClick={(e) => { if (e.target === e.currentTarget && !record.isPending) onClose() }}
    >
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-zinc-900">Record income</h2>
        <p className="mt-1 text-sm text-zinc-600">{stream.name}</p>
        <p className="mt-1 text-xs text-zinc-500">
          Default {stream.amount_paise != null ? formatPaise(stream.amount_paise) : '—'} · {stream.frequency}
        </p>

        <form
          className="mt-4 space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (!canSubmit) return
            record.mutate(undefined, { onSuccess: () => onClose() })
          }}
        >
          <label className="block text-xs font-medium text-zinc-700">
            Payment date
            <input
              type="date"
              className={inputCls}
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </label>

          <label className="block text-xs font-medium text-zinc-700">
            Deposit to
            <select
              className={inputCls}
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              required={stream.default_account_id == null}
            >
              <option value="">— select account —</option>
              {bankAccounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}{a.institution ? ` · ${a.institution}` : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-xs font-medium text-zinc-700">
            Amount override (₹)
            <input
              className={inputNumCls}
              inputMode="decimal"
              placeholder={
                stream.amount_paise != null ? String(stream.amount_paise / 100) : 'Amount'
              }
              value={amountOverride}
              onChange={(e) => setAmountOverride(e.target.value)}
            />
          </label>

          <label className="block text-xs font-medium text-zinc-700">
            Category
            <input
              className={inputCls}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="Salary"
            />
          </label>

          <label className="flex items-center gap-2 text-sm text-zinc-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-zinc-300 text-emerald-700"
              checked={rememberAccount}
              onChange={(e) => setRememberAccount(e.target.checked)}
            />
            Remember this bank account
          </label>

          {record.isError ? (
            <p className="text-sm text-red-600">{String(record.error)}</p>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              className="rounded-lg border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
              onClick={onClose}
              disabled={record.isPending}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {record.isPending ? 'Recording…' : 'Record income'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function IncomeRow({
  row,
  bankAccounts,
  onSave,
  onDelete,
  onRecordIncome,
  busy,
}: {
  row: IncomeOut
  bankAccounts: AccountOut[]
  onSave: (body: {
    name: string
    type: string
    amount_paise: number | null
    frequency: string
    taxability: string
    is_active: boolean
    default_account_id?: number | null
    category?: string | null
  }) => void
  onDelete: () => void
  onRecordIncome: () => void
  busy: boolean
}) {
  const [name, setName] = useState(row.name)
  const [type, setType] = useState(row.type)
  const [amt, setAmt] = useState(row.amount_paise != null ? String(row.amount_paise / 100) : '')
  const [freq, setFreq] = useState(row.frequency)
  const [tax, setTax] = useState(row.taxability)
  const [active, setActive] = useState(row.is_active)
  const [defaultAccount, setDefaultAccount] = useState(
    row.default_account_id != null ? String(row.default_account_id) : '',
  )
  const [category, setCategory] = useState(row.category ?? '')

  return (
    <tr className="border-t border-zinc-100">
      <td className="px-4 py-2 align-top">
        <input
          className="w-full min-w-[8rem] rounded border border-zinc-200 px-2 py-1 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 align-top">
        <select
          className="rounded border border-zinc-200 px-1 py-1 text-sm"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          {INCOME_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2 text-right align-top">
        <input
          className="w-24 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
          inputMode="decimal"
          value={amt}
          onChange={(e) => setAmt(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 align-top">
        <select
          className="rounded border border-zinc-200 px-1 py-1 text-sm"
          value={freq}
          onChange={(e) => setFreq(e.target.value)}
        >
          {INCOME_FREQUENCIES.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2 align-top">
        <select
          className="rounded border border-zinc-200 px-1 py-1 text-sm"
          value={tax}
          onChange={(e) => setTax(e.target.value)}
        >
          {TAXABILITY.map((t) => (
            <option key={t} value={t}>
              {t.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2 align-top">
        <select
          className="max-w-[8rem] rounded border border-zinc-200 px-1 py-1 text-sm"
          value={defaultAccount}
          onChange={(e) => setDefaultAccount(e.target.value)}
        >
          <option value="">—</option>
          {bankAccounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2 align-top">
        <input
          className="w-24 rounded border border-zinc-200 px-2 py-1 text-sm"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          placeholder="Salary"
        />
      </td>
      <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
        {formatPaiseCompact(row.monthly_equivalent_paise)}
      </td>
      <td className="px-4 py-2 align-top">
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
          aria-label="Active"
        />
      </td>
      <td className="px-4 py-2 align-top">
        <div className="flex flex-col gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-900 hover:bg-emerald-100 disabled:opacity-50"
            onClick={onRecordIncome}
          >
            Record income
          </button>
          <div className="flex gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded border border-zinc-200 px-2 py-1 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50"
            onClick={() => {
              const p = amt.trim() === '' ? null : rupeesToPaise(amt)
              if (p == null && amt.trim() !== '') {
                return
              }
              const acctId = defaultAccount.trim() === ''
                ? null
                : Number.parseInt(defaultAccount, 10) || null
              onSave({
                name: name.trim() || row.name,
                type,
                amount_paise: p,
                frequency: freq,
                taxability: tax,
                is_active: active,
                default_account_id: acctId,
                category: category.trim() || null,
              })
            }}
          >
            Save
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded border border-red-200 px-2 py-1 text-xs text-red-800 hover:bg-red-50 disabled:opacity-50"
            onClick={() => {
              if (window.confirm('Remove this income stream?')) {
                onDelete()
              }
            }}
          >
            Delete
          </button>
          </div>
        </div>
      </td>
    </tr>
  )
}
