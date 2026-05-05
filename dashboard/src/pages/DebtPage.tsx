import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, useMemo, useState } from 'react'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { DEBT_STATUS, DEBT_TYPES } from '@/constants/debt'
import {
  deleteDebt,
  fetchDebtAmortization,
  fetchDebts,
  fetchDebtSummary,
  postDebt,
  putDebt,
  syncDebtBalance,
} from '@/lib/api'
import type { AmortizationRow, DebtOut } from '@/types/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'


// ── tenure dropdown options ──────────────────────────────────────────────────
const TENURE_OPTIONS: { label: string; value: number }[] = [
  { label: '3 months', value: 3 },
  { label: '6 months', value: 6 },
  { label: '9 months', value: 9 },
  ...Array.from({ length: 25 }, (_, i) => ({
    label: `${i + 1} ${i === 0 ? 'year' : 'years'}`,
    value: (i + 1) * 12,
  })),
]

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) return null
  return Math.round(n * 100)
}

/** Months elapsed since a reference date (capped at tenure). */
function computeEmisPaid(firstEmiDate: string | null, tenureMonths: number | null): number {
  if (!firstEmiDate) return 0
  const ref = new Date(firstEmiDate)
  const today = new Date()
  const months =
    (today.getFullYear() - ref.getFullYear()) * 12 + (today.getMonth() - ref.getMonth())
  return Math.max(0, Math.min(months, tenureMonths ?? 9999))
}

/** Compute month label for a date offset by N months. */
function addMonths(dateStr: string, n: number): string {
  const d = new Date(dateStr)
  d.setMonth(d.getMonth() + n)
  return d.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}

/** PMT — monthly EMI for reduce-EMI prepay scenario. */
function pmt(rate: number, nper: number, pv: number): number {
  if (rate === 0) return pv / nper
  return (pv * rate * Math.pow(1 + rate, nper)) / (Math.pow(1 + rate, nper) - 1)
}

/** Re-simulate future schedule from a starting balance. Returns { futureInterest, months }. */
function simulateFromBalance(
  balance: number,
  monthlyRate: number,
  emi: number,
): { futureInterest: number; months: number } {
  if (balance <= 0 || emi <= 0) return { futureInterest: 0, months: 0 }
  let b = balance
  let months = 0
  let futureInterest = 0
  while (b > 0.01 && months < 1200) {
    const interest = b * monthlyRate
    const principal = emi - interest
    if (principal <= 0) break
    futureInterest += interest
    b = Math.max(0, b - principal)
    months++
  }
  return { futureInterest, months }
}

/** Each month pays EMI + extra toward principal (after interest). */
function simulateFromBalanceWithExtra(
  balance: number,
  monthlyRate: number,
  emi: number,
  extraPaise: number,
): { futureInterest: number; months: number } {
  const payment = emi + extraPaise
  if (balance <= 0 || payment <= 0) return { futureInterest: 0, months: 0 }
  let b = balance
  let months = 0
  let futureInterest = 0
  while (b > 0.01 && months < 1200) {
    const interest = b * monthlyRate
    const principal = payment - interest
    if (principal <= 0) break
    futureInterest += interest
    b = Math.max(0, b - principal)
    months++
  }
  return { futureInterest, months }
}

/** Month-by-month schedule from current balance with EMI + extra (same math as simulateFromBalanceWithExtra). */
type ExtraEmiScheduleRow = {
  seq: number
  payment_paise: number
  interest_paise: number
  principal_paise: number
  balance_after_paise: number
}

function buildExtraEmiSchedule(
  balance: number,
  monthlyRate: number,
  emi: number,
  extraPaise: number,
): ExtraEmiScheduleRow[] {
  const payment = emi + extraPaise
  const out: ExtraEmiScheduleRow[] = []
  if (balance <= 0 || payment <= 0) return out
  let b = balance
  let seq = 0
  while (b > 0.01 && seq < 1200) {
    seq++
    const interest = b * monthlyRate
    const principal = payment - interest
    if (principal <= 0) break
    const newB = Math.max(0, b - principal)
    const intR = Math.round(interest)
    const prinR = Math.round(b - newB)
    const payR = Math.round(Math.min(payment, intR + prinR))
    out.push({
      seq,
      payment_paise: payR,
      interest_paise: intR,
      principal_paise: prinR,
      balance_after_paise: Math.round(newB),
    })
    b = newB
  }
  return out
}

/** Principal balance after exactly `nMonths` payments (EMI + optional extra each month). */
function balanceAfterNMonths(
  startBalance: number,
  monthlyRate: number,
  emi: number,
  extraPaise: number,
  nMonths: number,
): number {
  if (nMonths <= 0) return Math.max(0, startBalance)
  const payment = emi + extraPaise
  if (startBalance <= 0 || payment <= 0) return 0
  let b = startBalance
  for (let m = 0; m < nMonths && b > 0.01; m++) {
    const interest = b * monthlyRate
    const principal = payment - interest
    if (principal <= 0) break
    b = Math.max(0, b - principal)
  }
  return b
}

/** Yearly principal left: baseline (before) vs EMI + extra each month (after). */
function yearlyRowsBeforeAfterExtra(
  startBalance: number,
  monthlyRate: number,
  emi: number,
  extraPaise: number,
): { label: string; before: number; after: number | null }[] {
  const out: { label: string; before: number; after: number | null }[] = [
    {
      label: 'Now',
      before: Math.round(startBalance),
      after: extraPaise > 0 ? Math.round(startBalance) : null,
    },
  ]
  for (let y = 1; y <= 60; y++) {
    const m = y * 12
    const b = balanceAfterNMonths(startBalance, monthlyRate, emi, 0, m)
    const a =
      extraPaise > 0 ? balanceAfterNMonths(startBalance, monthlyRate, emi, extraPaise, m) : null
    out.push({
      label: `After ${y} year${y === 1 ? '' : 's'}`,
      before: Math.round(b),
      after: a !== null ? Math.round(a) : null,
    })
    if (b < 1 && (a === null || a < 1)) break
  }
  return out
}

/** Yearly principal left: no prepay (before) vs lump prepay now then same EMI (after). */
function yearlyRowsBeforeAfterPrepay(
  startBalance: number,
  monthlyRate: number,
  emi: number,
  balanceAfterPrepay: number | null,
): { label: string; before: number; after: number | null }[] {
  const out: { label: string; before: number; after: number | null }[] = [
    {
      label: 'Now',
      before: Math.round(startBalance),
      after: balanceAfterPrepay != null ? Math.round(balanceAfterPrepay) : null,
    },
  ]
  for (let y = 1; y <= 60; y++) {
    const m = y * 12
    const b = balanceAfterNMonths(startBalance, monthlyRate, emi, 0, m)
    const a =
      balanceAfterPrepay != null
        ? balanceAfterNMonths(balanceAfterPrepay, monthlyRate, emi, 0, m)
        : null
    out.push({
      label: `After ${y} year${y === 1 ? '' : 's'}`,
      before: Math.round(b),
      after: a !== null ? Math.round(a) : null,
    })
    if (b < 1 && (a === null || a < 1)) break
  }
  return out
}

// ── main page ────────────────────────────────────────────────────────────────

export function DebtPage() {
  const qc = useQueryClient()
  const [openId, setOpenId] = useState<number | null>(null)

  const summary = useQuery({
    queryKey: ['debt-summary'],
    queryFn: fetchDebtSummary,
  })

  const debts = useQuery({
    queryKey: ['debts'],
    queryFn: fetchDebts,
  })

  const amort = useQuery({
    queryKey: ['debt-amort', openId],
    queryFn: () => fetchDebtAmortization(openId!),
    enabled: openId != null,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['debts'] })
    void qc.invalidateQueries({ queryKey: ['debt-summary'] })
    void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    void qc.invalidateQueries({ queryKey: ['net-worth-history'] })
  }

  const create = useMutation({ mutationFn: postDebt, onSuccess: invalidate })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof putDebt>[1] }) =>
      putDebt(id, body),
    onSuccess: (_data, { id }) => {
      invalidate()
      // Schedule + total interest come from amortization API; must refetch after rate/tenure/EMI edits
      void qc.invalidateQueries({ queryKey: ['debt-amort', id] })
    },
  })
  const remove = useMutation({
    mutationFn: deleteDebt,
    onSuccess: () => { setOpenId(null); invalidate() },
  })
  const syncBal = useMutation({
    mutationFn: syncDebtBalance,
    onSuccess: () => {
      invalidate()
      void qc.invalidateQueries({ queryKey: ['debt-amort', openId] })
    },
  })

  // ── add form state ──────────────────────────────────────────────────────
  const [nName, setNName] = useState('New loan')
  const [nLender, setNLender] = useState('')
  const [nType, setNType] = useState<string>(DEBT_TYPES[0])
  const [nOrig, setNOrig] = useState('')
  const [nBal, setNBal] = useState('100000')
  const [nEmi, setNEmi] = useState('')
  const [nRate, setNRate] = useState('8.5')
  const [nTenure, setNTenure] = useState<string>('')
  const [nStart, setNStart] = useState('')
  const [nFirstEmi, setNFirstEmi] = useState('')
  const [nFullEmiStart, setNFullEmiStart] = useState('')
  const [nNext, setNNext] = useState('')
  const [nStatus, setNStatus] = useState<string>(DEBT_STATUS[0])

  const payoffOrders = useMemo(() => {
    const active = (debts.data ?? []).filter((d) => d.status === 'active')
    return {
      avalanche: [...active].sort((a, b) => (b.rate_percent ?? 0) - (a.rate_percent ?? 0)),
      snowball: [...active].sort((a, b) => a.current_balance_paise - b.current_balance_paise),
    }
  }, [debts.data])

  if (summary.isPending || debts.isPending) return <PageLoading lines={4} />
  if (summary.isError || debts.isError) {
    return (
      <PageError
        title="Could not load debt data"
        message={<p className="text-sm">{String(summary.error ?? debts.error)}</p>}
      />
    )
  }

  const s = summary.data

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Liabilities"
        title="Debt"
        description="Loans & revolving balances · refreshes every 30s"
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard tone="balance" label="Outstanding" value={formatPaiseCompact(s.total_outstanding_paise)} />
        <KpiCard tone="balance" label="Monthly EMI" value={formatPaise(s.total_emi_monthly_paise)} />
        <KpiCard tone="neutral" label="Active loans" value={String(s.active_count)} />
        <KpiCard
          tone="neutral"
          label="Next EMI"
          value={s.next_emi_date ?? '—'}
          hint={s.next_emi_debt_name ?? undefined}
        />
      </section>

      {/* Payoff strategies */}
      {payoffOrders.avalanche.length > 0 && (
        <section>
          <SectionTitle>Payoff strategies</SectionTitle>
          <Panel>
            <p className="mt-1 text-sm text-zinc-600">
              Suggested priority for <span className="font-medium text-zinc-800">active</span>{' '}
              loans only. Bank EMIs stay the same — use this to decide where to put extra principal.
            </p>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-emerald-200/80 bg-emerald-50/50 p-4">
                <p className="text-sm font-semibold text-emerald-900">Avalanche (highest APR first)</p>
                <p className="mt-1 text-xs text-emerald-800/90">Minimises total interest paid.</p>
                <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-zinc-900">
                  {payoffOrders.avalanche.map((d) => (
                    <li key={d.id} className="leading-snug">
                      <span className="font-medium">{d.name}</span>
                      <span className="block text-xs text-zinc-600 sm:inline sm:before:content-['_·_']">
                        {formatPaiseCompact(d.current_balance_paise)}
                        {d.rate_percent != null ? ` @ ${d.rate_percent.toFixed(2)}% p.a.` : ''}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
              <div className="rounded-lg border border-sky-200/80 bg-sky-50/50 p-4">
                <p className="text-sm font-semibold text-sky-900">Snowball (smallest balance first)</p>
                <p className="mt-1 text-xs text-sky-900/90">Quick wins; motivation-focused.</p>
                <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-zinc-900">
                  {payoffOrders.snowball.map((d) => (
                    <li key={d.id} className="leading-snug">
                      <span className="font-medium">{d.name}</span>
                      <span className="block text-xs text-zinc-600 sm:inline sm:before:content-['_·_']">
                        {formatPaiseCompact(d.current_balance_paise)}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </Panel>
        </section>
      )}

      {/* Add debt */}
      <section>
        <SectionTitle>Add debt</SectionTitle>
        <Panel>
          <form
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault()
              const bal = rupeesToPaise(nBal)
              if (bal == null) return
              const orig = nOrig.trim() === '' ? null : rupeesToPaise(nOrig)
              const emi = nEmi.trim() === '' ? null : rupeesToPaise(nEmi)
              if (nOrig.trim() !== '' && orig == null) return
              if (nEmi.trim() !== '' && emi == null) return
              const rate = nRate.trim() === '' ? null : Number.parseFloat(nRate)
              const tenure = nTenure === '' ? null : Number.parseInt(nTenure, 10)
              create.mutate({
                name: nName.trim() || 'Debt',
                lender: nLender.trim() || null,
                type: nType,
                original_amount_paise: orig,
                current_balance_paise: bal,
                emi_paise: emi,
                rate_percent: rate != null && !Number.isNaN(rate) ? rate : null,
                start_date: nStart.trim() || null,
                next_emi_date: nNext.trim() || null,
                status: nStatus,
                tenure_months: tenure,
                first_emi_date: nFirstEmi.trim() || null,
                full_emi_start_date: nFullEmiStart.trim() || null,
              })
            }}
          >
            <label className="text-xs font-medium text-zinc-600">
              Name
              <input className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nName} onChange={(e) => setNName(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Lender
              <input className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nLender} onChange={(e) => setNLender(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Type
              <select className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nType} onChange={(e) => setNType(e.target.value)}>
                {DEBT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Tenure
              <select className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nTenure} onChange={(e) => setNTenure(e.target.value)}>
                <option value="">— select tenure —</option>
                {TENURE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Original amount (₹)
              <input className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={nOrig} onChange={(e) => setNOrig(e.target.value)} placeholder="optional" />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Current balance (₹) *
              <input className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={nBal} onChange={(e) => setNBal(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              EMI (₹/mo)
              <input className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={nEmi} onChange={(e) => setNEmi(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Rate % p.a.
              <input className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={nRate} onChange={(e) => setNRate(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Loan start date
              <input type="date" className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nStart} onChange={(e) => setNStart(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              First EMI date
              <input type="date" className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nFirstEmi} onChange={(e) => setNFirstEmi(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Full EMI starts
              <input type="date" className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nFullEmiStart} onChange={(e) => setNFullEmiStart(e.target.value)} placeholder="Home loans only" />
              <span className="mt-0.5 block text-[10px] text-zinc-400">Home loans: date full EMI begins (defaults to last disbursal)</span>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Next EMI date
              <input type="date" className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nNext} onChange={(e) => setNNext(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Status
              <select className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm" value={nStatus} onChange={(e) => setNStatus(e.target.value)}>
                {DEBT_STATUS.map((st) => <option key={st} value={st}>{st}</option>)}
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={create.isPending}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
              >
                Add debt
              </button>
            </div>
          </form>
          {create.isError ? <p className="mt-2 text-sm text-red-600">{String(create.error)}</p> : null}
        </Panel>
      </section>

      {/* Your loans */}
      <section>
        <SectionTitle>Your loans</SectionTitle>
        <Panel variant="table" padding={false} className="overflow-x-auto">
          <table className="w-full min-w-[1400px] table-fixed border-collapse text-left text-sm">
            <colgroup>
              <col className="w-[10%]" />
              <col className="w-[8%]" />
              <col className="w-[8%]" />
              <col className="w-[8%]" />
              <col className="w-[7%]" />
              <col className="w-[6%]" />
              <col className="w-[6%]" />
              <col className="w-[8%]" />
              <col className="w-[8%]" />
              <col className="w-[8%]" />
              <col className="w-[7%]" />
              <col className="w-[16%]" />
            </colgroup>
            <thead className="border-b border-zinc-200 bg-zinc-50">
              <tr className="text-xs font-semibold uppercase tracking-wide text-zinc-600">
                <th className="px-3 py-3">Name</th>
                <th className="px-3 py-3">Type</th>
                <th className="px-3 py-3">Lender</th>
                <th className="px-3 py-3 text-right">Balance</th>
                <th className="px-3 py-3 text-right">EMI</th>
                <th className="px-3 py-3 text-right">Rate %</th>
                <th className="px-3 py-3 text-right">Tenure</th>
                <th className="px-3 py-3">First EMI</th>
                <th className="px-3 py-3">Next EMI</th>
                <th className="px-3 py-3 text-right">Original</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200">
              {debts.data.length === 0 ? (
                <tr>
                  <td colSpan={12} className="px-4 py-8 text-center text-zinc-500">
                    No debts — add one above or run <code className="text-xs">make seed-demo</code>
                  </td>
                </tr>
              ) : (
                debts.data.map((d) => (
                  <Fragment key={d.id}>
                    <DebtEditRow
                      d={d}
                      busy={update.isPending || remove.isPending}
                      openId={openId}
                      setOpenId={setOpenId}
                      onSave={(body) => update.mutate({ id: d.id, body })}
                      onDelete={() => remove.mutate(d.id)}
                    />
                    {/* Expanded analytics panel */}
                    {openId === d.id && (
                      <tr className="bg-zinc-50/80">
                        <td colSpan={12} className="px-5 py-5">
                          {amort.isPending ? (
                            <p className="text-sm text-zinc-500">Loading schedule…</p>
                          ) : amort.isError ? (
                            <p className="text-sm text-red-600">Could not load amortization. Make sure rate %, EMI and tenure are set.</p>
                          ) : (
                            <DebtAnalyticsPanel
                              debt={d}
                              rows={amort.data?.rows ?? []}
                              isPhased={amort.data?.is_phased ?? false}
                              totalPreEmiMonths={amort.data?.total_pre_emi_months ?? 0}
                              onSyncBalance={() => syncBal.mutate(d.id)}
                              syncBusy={syncBal.isPending}
                            />
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </Panel>
      </section>
      {update.isError ? <p className="text-sm text-red-600">{String(update.error)}</p> : null}
      {remove.isError ? <p className="text-sm text-red-600">{String(remove.error)}</p> : null}
    </div>
  )
}

// ── DebtEditRow ───────────────────────────────────────────────────────────────

function DebtEditRow({
  d,
  busy,
  openId,
  setOpenId,
  onSave,
  onDelete,
}: {
  d: DebtOut
  busy: boolean
  openId: number | null
  setOpenId: (n: number | null) => void
  onSave: (body: Partial<DebtOut>) => void
  onDelete: () => void
}) {
  const [name, setName] = useState(d.name)
  const [lender, setLender] = useState(d.lender ?? '')
  const [type, setType] = useState(d.type)
  const [orig, setOrig] = useState(d.original_amount_paise != null ? String(d.original_amount_paise / 100) : '')
  const [bal, setBal] = useState(String(d.current_balance_paise / 100))
  const [emi, setEmi] = useState(d.emi_paise != null ? String(d.emi_paise / 100) : '')
  const [rate, setRate] = useState(d.rate_percent != null ? String(d.rate_percent) : '')
  const [tenure, setTenure] = useState(d.tenure_months != null ? String(d.tenure_months) : '')
  const [firstEmi, setFirstEmi] = useState(d.first_emi_date ?? '')
  const [next, setNext] = useState(d.next_emi_date ?? '')
  const [status, setStatus] = useState(d.status)

  const save = () => {
    const b = rupeesToPaise(bal)
    if (b == null) return
    const o = orig.trim() === '' ? null : rupeesToPaise(orig)
    const e = emi.trim() === '' ? null : rupeesToPaise(emi)
    if (orig.trim() !== '' && o == null) return
    if (emi.trim() !== '' && e == null) return
    const rp = rate.trim() === '' ? null : Number.parseFloat(rate)
    const tm = tenure === '' ? null : Number.parseInt(tenure, 10)
    onSave({
      name: name.trim() || d.name,
      lender: lender.trim() || null,
      type,
      original_amount_paise: o,
      current_balance_paise: b,
      emi_paise: e,
      rate_percent: rp != null && !Number.isNaN(rp) ? rp : null,
      next_emi_date: next.trim() || null,
      status,
      tenure_months: tm,
      first_emi_date: firstEmi.trim() || null,
    })
  }

  const cls = 'w-full min-w-0 rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-900 shadow-sm focus:border-emerald-500 focus:outline-none'
  const numCls = `${cls} text-right tabular-nums`
  const dateCls = `${cls} [color-scheme:light]`

  return (
    <tr className="align-top hover:bg-zinc-50/90">
      <td className="px-3 py-2.5"><input className={cls} value={name} onChange={(e) => setName(e.target.value)} /></td>
      <td className="px-3 py-2.5">
        <select className={cls} value={type} onChange={(e) => setType(e.target.value)}>
          {DEBT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </td>
      <td className="px-3 py-2.5"><input className={cls} value={lender} onChange={(e) => setLender(e.target.value)} /></td>
      <td className="px-3 py-2.5"><input className={numCls} inputMode="decimal" value={bal} onChange={(e) => setBal(e.target.value)} /></td>
      <td className="px-3 py-2.5"><input className={numCls} inputMode="decimal" value={emi} onChange={(e) => setEmi(e.target.value)} placeholder="—" /></td>
      <td className="px-3 py-2.5"><input className={numCls} inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} /></td>
      <td className="px-3 py-2.5">
        <select className={cls} value={tenure} onChange={(e) => setTenure(e.target.value)}>
          <option value="">—</option>
          {TENURE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </td>
      <td className="px-3 py-2.5"><input type="date" className={dateCls} value={firstEmi} onChange={(e) => setFirstEmi(e.target.value)} /></td>
      <td className="px-3 py-2.5"><input type="date" className={dateCls} value={next} onChange={(e) => setNext(e.target.value)} /></td>
      <td className="px-3 py-2.5"><input className={numCls} inputMode="decimal" placeholder="Optional" value={orig} onChange={(e) => setOrig(e.target.value)} /></td>
      <td className="px-3 py-2.5">
        <select className={cls} value={status} onChange={(e) => setStatus(e.target.value)}>
          {DEBT_STATUS.map((st) => <option key={st} value={st}>{st}</option>)}
        </select>
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-col items-stretch gap-1.5">
          <button
            type="button" disabled={busy}
            className="rounded-md bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
            onClick={save}
          >Save</button>
          <button
            type="button"
            className="rounded-md border border-emerald-200 bg-white px-2.5 py-1.5 text-xs font-medium text-emerald-800 shadow-sm hover:bg-emerald-50"
            onClick={() => setOpenId(openId === d.id ? null : d.id)}
          >
            {openId === d.id ? 'Hide analytics ▲' : 'Analytics ▼'}
          </button>
          <button
            type="button" disabled={busy}
            className="rounded-md border border-red-200 bg-white px-2.5 py-1.5 text-xs font-medium text-red-700 shadow-sm hover:bg-red-50 disabled:opacity-50"
            onClick={() => { if (window.confirm('Delete this debt record?')) onDelete() }}
          >Delete</button>
        </div>
      </td>
    </tr>
  )
}

// ── DebtAnalyticsPanel ────────────────────────────────────────────────────────

function DebtAnalyticsPanel({
  debt,
  rows,
  isPhased,
  totalPreEmiMonths,
  onSyncBalance,
  syncBusy,
}: {
  debt: DebtOut
  rows: AmortizationRow[]
  isPhased: boolean
  totalPreEmiMonths: number
  onSyncBalance: () => void
  syncBusy: boolean
}) {
  const [prepayInput, setPrepayInput] = useState('')
  const [extraEmiInput, setExtraEmiInput] = useState('')
  const [showTable, setShowTable] = useState(false)
  const [showExtraSchedule, setShowExtraSchedule] = useState(false)

  const totalEMIs = rows.length
  const fullEmiRows = rows.filter((r) => r.phase === 'full_emi')

  // For phased loans: EMIs paid counts only full-EMI phase rows
  const emisPaid = (() => {
    if (isPhased) {
      // Count full-EMI rows that correspond to months elapsed since first_emi_date
      const phasedEmisPaid = computeEmisPaid(debt.first_emi_date, fullEmiRows.length)
      return totalPreEmiMonths + Math.min(phasedEmisPaid, fullEmiRows.length)
    }
    return computeEmisPaid(debt.first_emi_date, debt.tenure_months)
  })()

  const totalInterest = rows.reduce((s, r) => s + r.interest_paise, 0)
  const interestPaid = rows.slice(0, emisPaid).reduce((s, r) => s + r.interest_paise, 0)
  const interestRemaining = totalInterest - interestPaid

  const principalOrig = debt.original_amount_paise ?? 0
  const principalRemaining = debt.current_balance_paise
  const principalPaid = principalOrig - principalRemaining

  const emi = debt.emi_paise ?? 0
  const rate = debt.rate_percent ?? 0
  const monthlyRate = rate / 100 / 12

  // Current EMI split from amortization (first upcoming full-EMI row)
  const nextFullEmiRow = rows[emisPaid] ?? null
  const currentInterestComp = nextFullEmiRow?.interest_paise
    ?? (principalRemaining > 0 && monthlyRate > 0 ? Math.round(principalRemaining * monthlyRate) : 0)
  const currentPrincipalComp = emi > 0 ? Math.max(0, emi - currentInterestComp) : 0
  const interestBleedPct = emi > 0 ? Math.round((currentInterestComp / emi) * 100) : 0

  const totalCost = principalOrig + totalInterest
  const interestMultiple = principalOrig > 0 ? totalInterest / principalOrig : 0

  const progressPct = totalEMIs > 0 ? Math.round((emisPaid / totalEMIs) * 100) : 0
  const remainingEMIs = Math.max(0, totalEMIs - emisPaid)

  const closureDate = (() => {
    const refDate = debt.first_emi_date || debt.start_date
    if (!refDate || totalEMIs === 0) return null
    return addMonths(refDate, totalEMIs)
  })()

  // Section 24(b) — interest in current FY (Apr–Mar)
  const fyInterest = (() => {
    if (!debt.start_date || rows.length === 0) return null
    const start = new Date(debt.start_date)
    // Current FY: Apr 2025 – Mar 2026 (based on today)
    const today = new Date()
    const fyStart = today.getMonth() >= 3
      ? new Date(today.getFullYear(), 3, 1)
      : new Date(today.getFullYear() - 1, 3, 1)
    const fyEnd = new Date(fyStart.getFullYear() + 1, 2, 31)
    let total = 0
    rows.forEach((r, i) => {
      const d = new Date(start)
      d.setMonth(d.getMonth() + i + 1)
      if (d >= fyStart && d <= fyEnd) total += r.interest_paise
    })
    return total
  })()

  // Prepayment calculator
  const prepayAmt = Number.parseFloat(prepayInput.replace(/,/g, '')) * 100 || 0

  const prepayCalc = useMemo(() => {
    if (prepayAmt <= 0 || emi <= 0 || monthlyRate <= 0) return null

    // Use amortization-based remaining balance for accuracy
    const currentAmortBalance =
      emisPaid > 0 && rows[emisPaid - 1]
        ? rows[emisPaid - 1].balance_after_paise
        : principalRemaining

    const newBalance = Math.max(0, currentAmortBalance - prepayAmt)
    if (newBalance <= 0) return null

    const remainingMonths = totalEMIs - emisPaid

    // Option A: Reduce tenure (keep same EMI)
    const { futureInterest: newFutureInterestA, months: newMonthsA } = simulateFromBalance(newBalance, monthlyRate, emi)
    const interestSavedA = interestRemaining - newFutureInterestA
    const monthsSavedA = remainingMonths - newMonthsA
    const newTotalInterestA = interestPaid + newFutureInterestA

    // Option B: Reduce EMI (keep same remaining tenure)
    const newEmiB = remainingMonths > 0 ? pmt(monthlyRate, remainingMonths, newBalance) : 0
    const newTotalInterestB = interestPaid + (newEmiB * remainingMonths - newBalance)
    const interestSavedB = totalInterest - newTotalInterestB

    return {
      reduceTenure: {
        monthsSaved: monthsSavedA,
        interestSaved: Math.round(interestSavedA),
        newTotalInterest: Math.round(newTotalInterestA),
        newClosureMonthsFromNow: newMonthsA,
      },
      reduceEmi: {
        newEmi: Math.round(newEmiB),
        emiSaved: Math.round(emi - newEmiB),
        interestSaved: Math.round(interestSavedB),
        newTotalInterest: Math.round(newTotalInterestB),
      },
    }
  }, [prepayAmt, emi, monthlyRate, rows, emisPaid, principalRemaining, totalEMIs, interestPaid, interestRemaining, totalInterest])

  const extraEmiPaise = Number.parseFloat(extraEmiInput.replace(/,/g, '')) * 100 || 0

  const extraEmiCalc = useMemo(() => {
    if (extraEmiPaise <= 0 || emi <= 0 || monthlyRate <= 0) return null

    const currentAmortBalance =
      emisPaid > 0 && rows[emisPaid - 1]
        ? rows[emisPaid - 1].balance_after_paise
        : principalRemaining

    if (currentAmortBalance <= 0) return null

    const baseline = simulateFromBalance(currentAmortBalance, monthlyRate, emi)
    const withExtra = simulateFromBalanceWithExtra(currentAmortBalance, monthlyRate, emi, extraEmiPaise)
    const scheduleRows = buildExtraEmiSchedule(currentAmortBalance, monthlyRate, emi, extraEmiPaise)

    const interestSaved = baseline.futureInterest - withExtra.futureInterest
    const monthsSaved = baseline.months - withExtra.months
    const newTotalInterest = interestPaid + withExtra.futureInterest

    return {
      baselineMonths: baseline.months,
      newMonths: withExtra.months,
      monthsSaved,
      interestSaved: Math.round(interestSaved),
      newTotalInterest: Math.round(newTotalInterest),
      totalMonthlyOutflow: emi + extraEmiPaise,
      scheduleRows,
    }
  }, [extraEmiPaise, emi, monthlyRate, rows, emisPaid, principalRemaining, interestPaid])

  const currentAmortForCheckpoints =
    emisPaid > 0 && rows[emisPaid - 1]
      ? rows[emisPaid - 1].balance_after_paise
      : principalRemaining

  const yearlyExtraCheckpoints = useMemo(() => {
    if (emi <= 0 || monthlyRate <= 0 || currentAmortForCheckpoints <= 0) return null
    return yearlyRowsBeforeAfterExtra(
      currentAmortForCheckpoints,
      monthlyRate,
      emi,
      extraEmiPaise,
    )
  }, [emi, monthlyRate, currentAmortForCheckpoints, extraEmiPaise])

  const yearlyPrepayCheckpoints = useMemo(() => {
    if (emi <= 0 || monthlyRate <= 0 || currentAmortForCheckpoints <= 0) return null
    if (prepayAmt <= 0) {
      return {
        rows: yearlyRowsBeforeAfterPrepay(currentAmortForCheckpoints, monthlyRate, emi, null),
        error: null as string | null,
      }
    }
    const nb = Math.max(0, currentAmortForCheckpoints - prepayAmt)
    if (nb <= 0) {
      return {
        rows: null as { label: string; before: number; after: number | null }[] | null,
        error: 'Prepay amount clears or exceeds principal left — no yearly comparison.',
      }
    }
    return {
      rows: yearlyRowsBeforeAfterPrepay(currentAmortForCheckpoints, monthlyRate, emi, nb),
      error: null as string | null,
    }
  }, [emi, monthlyRate, currentAmortForCheckpoints, prepayAmt])

  if (totalEMIs === 0) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-zinc-500">
          No amortization data — set <strong>rate %</strong>, <strong>EMI</strong>, and <strong>tenure</strong> on this loan to see analytics.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {isPhased && (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-2 text-xs text-blue-700">
          Phased home loan — {totalPreEmiMonths} months pre-EMI (interest-only) + {fullEmiRows.length} months full EMI
        </div>
      )}

      {/* ── EMI progress ── */}
      <div>
        <div className="mb-1.5 flex items-center justify-between text-sm">
          <span className="font-medium text-zinc-700">
            {emisPaid} of {totalEMIs} EMIs paid
            <span className="ml-2 text-zinc-400">({progressPct}% complete)</span>
          </span>
          {closureDate && <span className="text-xs text-zinc-500">Closes {closureDate}</span>}
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-zinc-100">
          <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${progressPct}%` }} />
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-zinc-400">
          <span>{remainingEMIs} EMIs remaining</span>
          <span>{Math.floor(remainingEMIs / 12)}y {remainingEMIs % 12}m left</span>
        </div>
      </div>

      {/* ── Balance tracker ── */}
      <div className="flex items-center gap-4 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Current balance (stored)</p>
          <p className="text-lg font-bold tabular-nums text-zinc-900">{formatPaiseCompact(debt.current_balance_paise)}</p>
        </div>
        {rows[emisPaid - 1] && (
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Estimated from schedule</p>
            <p className="text-lg font-bold tabular-nums text-emerald-700">{formatPaiseCompact(rows[emisPaid - 1].balance_after_paise)}</p>
          </div>
        )}
        {!debt.first_emi_date && (
          <p className="text-xs text-amber-600">Set first EMI date in the table above for accurate balance sync</p>
        )}
        {debt.first_emi_date && (
          <button
            type="button"
            onClick={onSyncBalance}
            disabled={syncBusy}
            className="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
          >
            {syncBusy ? 'Syncing…' : '↺ Sync from schedule'}
          </button>
        )}
      </div>

      {/* ── 4-tile principal/interest grid ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: 'Principal paid', value: formatPaiseCompact(principalPaid), sub: `of ${formatPaiseCompact(principalOrig)}`, color: 'emerald' },
          { label: 'Principal left', value: formatPaiseCompact(principalRemaining), sub: `${principalOrig > 0 ? Math.round((principalRemaining / principalOrig) * 100) : 0}% remaining`, color: 'zinc' },
          { label: 'Interest paid', value: formatPaiseCompact(interestPaid), sub: 'so far', color: 'amber' },
          { label: 'Interest left', value: formatPaiseCompact(interestRemaining), sub: 'still to pay', color: 'red' },
        ].map((k) => (
          <div key={k.label} className={`rounded-xl border p-3 ${
            k.color === 'red' ? 'border-red-100 bg-red-50'
            : k.color === 'amber' ? 'border-amber-100 bg-amber-50'
            : k.color === 'emerald' ? 'border-emerald-100 bg-emerald-50'
            : 'border-zinc-100 bg-zinc-50'
          }`}>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{k.label}</p>
            <p className={`mt-0.5 text-lg font-bold tabular-nums ${
              k.color === 'red' ? 'text-red-700'
              : k.color === 'amber' ? 'text-amber-700'
              : k.color === 'emerald' ? 'text-emerald-700'
              : 'text-zinc-800'
            }`}>{k.value}</p>
            <p className="mt-0.5 text-[11px] text-zinc-400">{k.sub}</p>
          </div>
        ))}
      </div>

      {/* ── Total cost of borrowing ── */}
      {principalOrig > 0 && (
        <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Total cost of borrowing</p>
          <p className="mb-3 text-xs text-zinc-500">
            Full amortization schedule:{' '}
            {rate > 0 ? <span className="font-medium text-zinc-700">{rate}% p.a.</span> : <span className="text-zinc-400">— rate</span>}
            {totalEMIs > 0 ? (
              <>
                {' · '}
                <span className="font-medium text-zinc-700">{totalEMIs} payments</span>
                {debt.tenure_months != null && (
                  <span className="text-zinc-400"> ({debt.tenure_months} mo tenure)</span>
                )}
              </>
            ) : null}
            . Edit rate or tenure in the row above, then <strong>Save</strong> — analytics use saved values only.
          </p>
          <div className="flex flex-wrap items-baseline gap-6">
            <div>
              <span className="text-2xl font-bold tabular-nums text-zinc-900">{formatPaiseCompact(totalCost)}</span>
              <span className="ml-2 text-sm text-zinc-400">total outgo</span>
            </div>
            <div>
              <span className="text-xl font-bold tabular-nums text-red-600">{formatPaiseCompact(totalInterest)}</span>
              <span className="ml-2 text-sm text-zinc-400">
                total interest ({(interestMultiple * 100).toFixed(0)}% of principal over the loan)
              </span>
            </div>
          </div>
          <p className="mt-1.5 text-xs text-zinc-400">
            For every ₹100 borrowed, you pay ₹{(100 + interestMultiple * 100).toFixed(0)} total.
          </p>
          <p className="mt-2 text-xs text-zinc-500">
            The percentage next to total interest is <strong>lifetime</strong> interest divided by original principal — not the same number as your annual % p.a. (e.g. 11% p.a. over several years still adds up to tens of percent of principal).
          </p>
        </div>
      )}

      {/* ── EMI bleed meter ── */}
      {emi > 0 && (
        <div className="rounded-xl border border-zinc-200 p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">This month's EMI breakdown</p>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <span className="text-2xl font-bold tabular-nums text-zinc-900">{formatPaise(emi)}</span>
            <span className="text-sm text-zinc-400">=</span>
            <span className="text-base font-semibold tabular-nums text-emerald-700">{formatPaise(currentPrincipalComp)} principal</span>
            <span className="text-sm text-zinc-400">+</span>
            <span className="text-base font-semibold tabular-nums text-red-600">{formatPaise(currentInterestComp)} interest</span>
          </div>
          <div className="flex h-3 overflow-hidden rounded-full">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${100 - interestBleedPct}%` }} />
            <div className="h-full bg-red-400 transition-all" style={{ width: `${interestBleedPct}%` }} />
          </div>
          <div className="mt-1.5 flex justify-between text-xs">
            <span className="text-emerald-600">{100 - interestBleedPct}% principal</span>
            <span className={interestBleedPct > 70 ? 'font-semibold text-red-600' : 'text-zinc-500'}>
              {interestBleedPct}% interest{interestBleedPct > 70 ? ' 🔴' : ''}
            </span>
          </div>
        </div>
      )}

      {/* ── Section 24(b) ── */}
      {fyInterest !== null && fyInterest > 0 && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-600">Section 24(b) — Home loan interest deduction</p>
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold tabular-nums text-blue-800">{formatPaiseCompact(fyInterest)}</span>
            <span className="text-sm text-blue-600">interest paid in current FY</span>
          </div>
          <p className="mt-1 text-xs text-blue-500">
            {fyInterest >= 20_000_00
              ? `₹2L limit maxed ✓ — deductible: ₹2,00,000`
              : `Deductible: ${formatPaise(fyInterest)} (limit ₹2L, ${formatPaise(Math.max(0, 20_000_00 - fyInterest))} unused)`}
          </p>
        </div>
      )}

      {/* ── Prepayment calculator ── */}
      <div className="rounded-xl border border-zinc-200 p-4">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Prepayment calculator</p>
        <p className="mb-3 text-xs text-zinc-500">
          Lump-sum off principal today. Scenarios below assume this balance before prepayment.
        </p>
        <div className="mb-3 flex flex-wrap items-baseline gap-4 rounded-lg border border-emerald-100 bg-emerald-50/50 px-3 py-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Principal left (now)</p>
            <p className="text-lg font-bold tabular-nums text-zinc-900">
              {formatPaiseCompact(
                emisPaid > 0 && rows[emisPaid - 1]
                  ? rows[emisPaid - 1].balance_after_paise
                  : principalRemaining,
              )}
            </p>
            <p className="text-[11px] text-zinc-400">balance before prepayment</p>
          </div>
        </div>
        <div className="flex items-center gap-3 mb-4">
          <label className="text-sm text-zinc-600">If I prepay (₹)</label>
          <input
            className="w-36 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={prepayInput}
            onChange={(e) => setPrepayInput(e.target.value)}
            placeholder="e.g. 200000"
          />
        </div>
        {prepayCalc ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {/* Option A: Reduce tenure */}
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
              <p className="mb-3 text-sm font-semibold text-emerald-900">Option A — Reduce tenure</p>
              <p className="mb-3 text-xs text-emerald-700">Same EMI ({formatPaise(emi)}), closes earlier</p>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Months saved', value: `${prepayCalc.reduceTenure.monthsSaved}m (${Math.floor(prepayCalc.reduceTenure.monthsSaved / 12)}y ${prepayCalc.reduceTenure.monthsSaved % 12}m)` },
                  { label: 'Interest saved', value: formatPaiseCompact(prepayCalc.reduceTenure.interestSaved), highlight: true },
                  { label: 'New total interest', value: formatPaiseCompact(prepayCalc.reduceTenure.newTotalInterest) },
                  { label: 'New closure', value: closureDate ? addMonths(debt.first_emi_date || debt.start_date!, prepayCalc.reduceTenure.newClosureMonthsFromNow + emisPaid) : '—' },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-emerald-100 bg-white px-3 py-2 text-center">
                    <p className="text-[10px] text-zinc-500">{item.label}</p>
                    <p className={`font-bold tabular-nums ${item.highlight ? 'text-emerald-700' : 'text-zinc-800'}`}>{item.value}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Option B: Reduce EMI */}
            <div className="rounded-xl border border-sky-200 bg-sky-50 p-4">
              <p className="mb-3 text-sm font-semibold text-sky-900">Option B — Reduce EMI</p>
              <p className="mb-3 text-xs text-sky-700">Same tenure, lower monthly payment</p>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'New EMI', value: formatPaise(prepayCalc.reduceEmi.newEmi) },
                  { label: 'EMI reduced by', value: formatPaise(prepayCalc.reduceEmi.emiSaved), highlight: true },
                  { label: 'Interest saved', value: formatPaiseCompact(prepayCalc.reduceEmi.interestSaved) },
                  { label: 'New total interest', value: formatPaiseCompact(prepayCalc.reduceEmi.newTotalInterest) },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg border border-sky-100 bg-white px-3 py-2 text-center">
                    <p className="text-[10px] text-zinc-500">{item.label}</p>
                    <p className={`font-bold tabular-nums ${item.highlight ? 'text-sky-700' : 'text-zinc-800'}`}>{item.value}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : prepayInput ? (
          <p className="text-sm text-zinc-400">Set EMI, rate %, and tenure to compute prepayment scenarios.</p>
        ) : null}
        {yearlyPrepayCheckpoints && (
          <div className="mt-4 border-t border-zinc-200 pt-4">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Yearly checkpoints — principal left
            </p>
            <p className="mb-2 text-xs text-zinc-500">
              <span className="font-medium text-zinc-700">Before</span> — regular EMI only from current balance.{' '}
              <span className="font-medium text-emerald-800">After</span> — prepay the amount above today, then same EMI (reduce-tenure path).
              {prepayAmt <= 0 ? ' Enter a prepay amount to fill After.' : null}
            </p>
            {yearlyPrepayCheckpoints.error ? (
              <p className="text-sm text-amber-800">{yearlyPrepayCheckpoints.error}</p>
            ) : yearlyPrepayCheckpoints.rows ? (
              <div className="max-h-56 overflow-auto rounded-lg border border-emerald-200/80 bg-white">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-emerald-50 text-zinc-600">
                    <tr>
                      <th className="px-3 py-2 text-left">When</th>
                      <th className="px-3 py-2 text-right">Before</th>
                      <th className="px-3 py-2 text-right">After</th>
                    </tr>
                  </thead>
                  <tbody>
                    {yearlyPrepayCheckpoints.rows.map((r) => (
                      <tr key={r.label} className="border-t border-zinc-100">
                        <td className="px-3 py-1.5 text-zinc-700">{r.label}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-medium text-zinc-900">
                          {formatPaise(r.before)}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-medium text-emerald-800">
                          {r.after != null ? formatPaise(r.after) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* ── Extra EMI (monthly overpayment) calculator ── */}
      <div className="rounded-xl border border-zinc-200 p-4">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">Extra EMI calculator</p>
        <p className="mb-3 text-xs text-zinc-500">
          Fixed amount <strong>on top of</strong> your regular EMI each month (applied to principal after interest). Compare to staying on the current schedule.
        </p>
        <div className="mb-3 flex flex-wrap items-baseline gap-4 rounded-lg border border-violet-100 bg-violet-50/50 px-3 py-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">Principal left (now)</p>
            <p className="text-lg font-bold tabular-nums text-zinc-900">
              {formatPaiseCompact(
                emisPaid > 0 && rows[emisPaid - 1]
                  ? rows[emisPaid - 1].balance_after_paise
                  : principalRemaining,
              )}
            </p>
            <p className="text-[11px] text-zinc-400">starting balance for projection below</p>
          </div>
        </div>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="text-sm text-zinc-600">Extra per month (₹)</label>
          <input
            className="w-36 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={extraEmiInput}
            onChange={(e) => setExtraEmiInput(e.target.value)}
            placeholder="e.g. 10000"
          />
          {emi > 0 && (
            <span className="text-xs text-zinc-400">
              Base EMI {formatPaise(emi)}
              {extraEmiCalc ? (
                <span className="text-zinc-600">
                  {' '}
                  → total outflow {formatPaise(extraEmiCalc.totalMonthlyOutflow)}/mo
                </span>
              ) : null}
            </span>
          )}
        </div>
        {extraEmiCalc ? (
          <div className="rounded-xl border border-violet-200 bg-violet-50 p-4">
            <p className="mb-3 text-sm font-semibold text-violet-900">If you pay this every month</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {[
                {
                  label: 'Months to close (vs baseline)',
                  value: `${extraEmiCalc.newMonths}m vs ${extraEmiCalc.baselineMonths}m`,
                  sub: `${extraEmiCalc.monthsSaved} month(s) sooner`,
                  bold: true,
                },
                {
                  label: 'Interest saved (future)',
                  value: formatPaiseCompact(extraEmiCalc.interestSaved),
                  sub: 'vs same schedule without extra',
                  bold: true,
                },
                {
                  label: 'New total interest (loan)',
                  value: formatPaiseCompact(extraEmiCalc.newTotalInterest),
                  sub: 'interest paid + future at new pace',
                  bold: false,
                },
                {
                  label: 'Approx. closure date',
                  value: (() => {
                    const ref = debt.first_emi_date || debt.start_date
                    if (!ref) return '—'
                    return addMonths(ref, emisPaid + extraEmiCalc.newMonths)
                  })(),
                  sub: 'from schedule start',
                  bold: false,
                },
              ].map((item) => (
                <div key={item.label} className="rounded-lg border border-violet-100 bg-white px-3 py-2 text-center">
                  <p className="text-[10px] text-zinc-500">{item.label}</p>
                  <p
                    className={`mt-0.5 font-bold tabular-nums text-zinc-800 ${item.bold ? 'text-violet-800' : ''}`}
                  >
                    {item.value}
                  </p>
                  <p className="mt-0.5 text-[11px] text-zinc-400">{item.sub}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 border-t border-violet-200 pt-3">
              <button
                type="button"
                className="text-xs font-medium text-violet-800 underline-offset-2 hover:underline"
                onClick={() => setShowExtraSchedule((v) => !v)}
              >
                {showExtraSchedule ? '▲ Hide' : '▼ Show'} projected amortization (EMI + extra)
                {extraEmiCalc.scheduleRows.length > 0
                  ? ` (${extraEmiCalc.scheduleRows.length} payments)`
                  : ''}
              </button>
              {showExtraSchedule && extraEmiCalc.scheduleRows.length > 0 ? (
                <div className="mt-2 max-h-72 overflow-auto rounded-lg border border-violet-200 bg-white">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-violet-100 text-violet-900">
                      <tr>
                        <th className="px-2 py-1.5 text-left">#</th>
                        <th className="px-2 py-1.5 text-right">Payment</th>
                        <th className="px-2 py-1.5 text-right">Interest</th>
                        <th className="px-2 py-1.5 text-right">Principal</th>
                        <th className="px-2 py-1.5 text-right">Balance</th>
                      </tr>
                    </thead>
                    <tbody>
                      {extraEmiCalc.scheduleRows.map((r) => (
                        <tr key={r.seq} className="border-t border-zinc-100">
                          <td className="px-2 py-1 tabular-nums text-zinc-600">{emisPaid + r.seq}</td>
                          <td className="px-2 py-1 text-right tabular-nums">{formatPaise(r.payment_paise)}</td>
                          <td className="px-2 py-1 text-right tabular-nums text-red-600">{formatPaise(r.interest_paise)}</td>
                          <td className="px-2 py-1 text-right tabular-nums text-emerald-700">{formatPaise(r.principal_paise)}</td>
                          <td className="px-2 py-1 text-right tabular-nums font-medium">{formatPaise(r.balance_after_paise)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : showExtraSchedule && extraEmiCalc.scheduleRows.length === 0 ? (
                <p className="mt-2 text-xs text-zinc-500">No remaining payments to simulate.</p>
              ) : null}
              <p className="mt-2 text-[11px] leading-relaxed text-violet-800/90">
                Projected from principal left above: each row is EMI + extra toward principal after interest. # is the month index on your full loan (same as the schedule below). Rounding or rate changes may differ from your lender.
              </p>
            </div>
          </div>
        ) : extraEmiInput ? (
          <p className="text-sm text-zinc-400">Set EMI, rate %, and tenure to compute extra-EMI impact.</p>
        ) : null}
        {yearlyExtraCheckpoints && (
          <div className="mt-4 border-t border-zinc-200 pt-4">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Yearly checkpoints — principal left
            </p>
            <p className="mb-2 text-xs text-zinc-500">
              <span className="font-medium text-zinc-700">Before</span> — regular EMI only.{' '}
              <span className="font-medium text-violet-800">After</span> — EMI + extra each month
              {extraEmiPaise <= 0 ? ' (enter extra per month above).' : '.'}
            </p>
            <div className="max-h-56 overflow-auto rounded-lg border border-violet-200/80 bg-white">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-violet-50 text-zinc-600">
                  <tr>
                    <th className="px-3 py-2 text-left">When</th>
                    <th className="px-3 py-2 text-right">Before</th>
                    <th className="px-3 py-2 text-right">After</th>
                  </tr>
                </thead>
                <tbody>
                  {yearlyExtraCheckpoints.map((r) => (
                    <tr key={r.label} className="border-t border-zinc-100">
                      <td className="px-3 py-1.5 text-zinc-700">{r.label}</td>
                      <td className="px-3 py-1.5 text-right tabular-nums font-medium text-zinc-900">
                        {formatPaise(r.before)}
                      </td>
                      <td className="px-3 py-1.5 text-right tabular-nums font-medium text-violet-900">
                        {r.after != null ? formatPaise(r.after) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ── Raw amortization table (collapsible) ── */}
      <div>
        <button
          type="button"
          className="text-xs text-zinc-500 underline-offset-2 hover:underline"
          onClick={() => setShowTable((v) => !v)}
        >
          {showTable ? '▲ Hide schedule' : '▼ Show full amortization schedule'} ({rows.length} rows)
        </button>
        {showTable && (
          <div className="mt-2 max-h-64 overflow-auto rounded-lg border border-zinc-200 bg-white">
            <table className="w-full text-xs">
              <thead className="bg-zinc-100 text-zinc-600">
                <tr>
                  <th className="px-2 py-1 text-left">#</th>
                  <th className="px-2 py-1 text-left">Phase</th>
                  <th className="px-2 py-1 text-right">Payment</th>
                  <th className="px-2 py-1 text-right">Interest</th>
                  <th className="px-2 py-1 text-right">Principal</th>
                  <th className="px-2 py-1 text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.month_index}
                    className={`border-t border-zinc-100 ${r.month_index <= emisPaid ? 'bg-zinc-50 text-zinc-400' : ''}`}
                  >
                    <td className="px-2 py-1">{r.month_index}</td>
                    <td className="px-2 py-1">
                      <span className={`rounded px-1 text-[10px] ${r.phase === 'pre_emi' ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
                        {r.phase === 'pre_emi' ? 'Pre-EMI' : 'EMI'}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums">{formatPaise(r.payment_paise)}</td>
                    <td className="px-2 py-1 text-right tabular-nums text-red-600">{formatPaise(r.interest_paise)}</td>
                    <td className="px-2 py-1 text-right tabular-nums text-emerald-700">{formatPaise(r.principal_paise)}</td>
                    <td className="px-2 py-1 text-right tabular-nums">{formatPaise(r.balance_after_paise)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

