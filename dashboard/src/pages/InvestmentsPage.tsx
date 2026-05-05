import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { Panel } from '@/components/ui/Panel'
import { FIXED_INCOME_TYPES, INVESTMENT_TYPES } from '@/constants/investments'
import {
  deleteFixedIncome,
  deleteInvestment,
  fetchFixedIncome,
  fetchFixedIncomeSummary,
  fetchInvestments,
  fetchPortfolioSummary,
  postFixedIncome,
  postInvestment,
  putFixedIncome,
  putInvestment,
} from '@/lib/api'
import type { FixedIncomeOut, InvestmentOut } from '@/types/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'


function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) {
    return null
  }
  return Math.round(n * 100)
}

/** Future value of monthly SIP (payment at month-end), paise out. */
function sipFutureValuePaise(monthlyPaise: number, annualCagrPercent: number, years: number): number {
  const n = Math.max(0, Math.floor(years * 12))
  const rm = annualCagrPercent / 100 / 12
  if (n === 0) {
    return 0
  }
  if (rm <= 0) {
    return monthlyPaise * n
  }
  return monthlyPaise * ((Math.pow(1 + rm, n) - 1) / rm)
}

/** SIP with annual step-up on the monthly amount (same month-end timing). */
function sipStepUpFutureValuePaise(
  initialMonthlyPaise: number,
  annualStepUpPercent: number,
  annualCagrPercent: number,
  years: number,
): number {
  const months = Math.max(0, Math.floor(years * 12))
  const rm = annualCagrPercent / 100 / 12
  let total = 0
  for (let m = 0; m < months; m++) {
    const yearIdx = Math.floor(m / 12)
    const monthly = initialMonthlyPaise * Math.pow(1 + annualStepUpPercent / 100, yearIdx)
    const remaining = months - m - 1
    if (remaining < 0) {
      continue
    }
    if (rm <= 0) {
      total += monthly
    } else {
      total += monthly * Math.pow(1 + rm, remaining)
    }
  }
  return Math.round(total)
}

export function InvestmentsPage() {
  const qc = useQueryClient()
  const [sipMonthly, setSipMonthly] = useState('15000')
  const [sipYears, setSipYears] = useState('15')
  const [sipCagr, setSipCagr] = useState('12')
  const [sipStepUp, setSipStepUp] = useState('10')

  const inv = useMutation({
    mutationFn: postInvestment,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['investments'] })
      void qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void qc.invalidateQueries({ queryKey: ['net-worth-history'] })
    },
  })

  const invUp = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: {
        instrument?: string
        type?: string
        isin_code?: string | null
        units?: number | null
        avg_price_paise?: number | null
        current_price_paise?: number | null
      }
    }) =>
      putInvestment(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['investments'] })
      void qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const invDel = useMutation({
    mutationFn: deleteInvestment,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['investments'] })
      void qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const fi = useMutation({
    mutationFn: postFixedIncome,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['fixed-income'] })
      void qc.invalidateQueries({ queryKey: ['fixed-income-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const fiUp = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: {
        institution?: string
        type?: string
        principal_paise?: number
        rate_percent?: number | null
        start_date?: string | null
        maturity_date?: string | null
      }
    }) =>
      putFixedIncome(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['fixed-income'] })
      void qc.invalidateQueries({ queryKey: ['fixed-income-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const fiDel = useMutation({
    mutationFn: deleteFixedIncome,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['fixed-income'] })
      void qc.invalidateQueries({ queryKey: ['fixed-income-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const portfolio = useQuery({
    queryKey: ['portfolio-summary'],
    queryFn: fetchPortfolioSummary,
  })

  const holdings = useQuery({
    queryKey: ['investments'],
    queryFn: fetchInvestments,
  })

  const fiSummary = useQuery({
    queryKey: ['fixed-income-summary'],
    queryFn: fetchFixedIncomeSummary,
  })

  const fiList = useQuery({
    queryKey: ['fixed-income'],
    queryFn: fetchFixedIncome,
  })

  const sipResult = useMemo(() => {
    const m = Number.parseFloat(sipMonthly.replace(/,/g, ''))
    const y = Number.parseFloat(sipYears)
    const c = Number.parseFloat(sipCagr)
    const step = Number.parseFloat(sipStepUp.replace(/,/g, ''))
    if (Number.isNaN(m) || m < 0 || Number.isNaN(y) || y < 0 || Number.isNaN(c)) {
      return null
    }
    const basePaise = Math.round(m * 100)
    if (Number.isNaN(step) || step <= 0) {
      return sipFutureValuePaise(basePaise, c, y)
    }
    return sipStepUpFutureValuePaise(basePaise, step, c, y)
  }, [sipMonthly, sipYears, sipCagr, sipStepUp])

  const [hiName, setHiName] = useState('Nifty 50 Index Fund')
  const [hiType, setHiType] = useState<string>(INVESTMENT_TYPES[0])
  const [hiIsin, setHiIsin] = useState('')
  const [hiUnits, setHiUnits] = useState('100')
  const [hiAvg, setHiAvg] = useState('250')
  const [hiCur, setHiCur] = useState('265')

  const [fiInst, setFiInst] = useState('PPF')
  const [fiType, setFiType] = useState<string>(FIXED_INCOME_TYPES[2])
  const [fiPrin, setFiPrin] = useState('150000')
  const [fiRate, setFiRate] = useState('7.1')
  const [fiStart, setFiStart] = useState('')
  const [fiMat, setFiMat] = useState('')

  if (portfolio.isPending || holdings.isPending || fiSummary.isPending || fiList.isPending) {
    return <PageLoading lines={4} showFooterBlock />
  }

  if (portfolio.isError || holdings.isError || fiSummary.isError || fiList.isError) {
    return (
      <PageError
        title="Could not load investments"
        message={<p className="text-sm">{String(portfolio.error ?? holdings.error)}</p>}
      />
    )
  }

  const p = portfolio.data
  const unrealPct =
    p.cost_basis_paise > 0 ? (p.unrealized_paise / p.cost_basis_paise) * 100 : null

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Portfolio"
        title="Investments"
        description={
          <>
            Market holdings & fixed income · refreshes every 30s. Listed prices sync daily around{' '}
            <strong>6:00</strong> (API scheduler, Asia/Kolkata). Use Yahoo tickers e.g.{' '}
            <code className="text-xs">RELIANCE.NS</code> in instrument for quotes.{' '}
            <Link to="/investments/stocks" className="font-medium text-emerald-800 underline">
              Stocks & ETFs
            </Link>{' '}
            — sector weights & LTCG/STCG tags.
          </>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard tone="neutral" label="Cost basis" value={formatPaiseCompact(p.cost_basis_paise)} />
        <KpiCard tone="neutral" label="Market value" value={formatPaiseCompact(p.market_value_paise)} />
        <KpiCard
          tone="spending"
          label="Unrealized P&L"
          value={formatPaise(p.unrealized_paise)}
          hint={unrealPct != null ? `${unrealPct >= 0 ? '+' : ''}${unrealPct.toFixed(1)}% vs cost` : undefined}
        />
        <KpiCard tone="neutral" label="Holdings" value={String(p.holdings_count)} />
      </section>

      <section>
        <SectionTitle>Fixed income</SectionTitle>
        <div className="mb-3 flex flex-wrap gap-4 text-sm text-zinc-600">
          <span>
            Total principal:{' '}
            <strong className="text-zinc-900">
              {formatPaiseCompact(fiSummary.data.total_principal_paise)}
            </strong>
          </span>
          <span>
            Instruments: <strong className="text-zinc-900">{fiSummary.data.instrument_count}</strong>
          </span>
        </div>

        <Panel className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-zinc-800">Add fixed income</h3>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              const pr = rupeesToPaise(fiPrin)
              if (pr == null) {
                return
              }
              const rt = fiRate.trim() === '' ? null : Number.parseFloat(fiRate)
              fi.mutate({
                institution: fiInst.trim() || 'Instrument',
                type: fiType,
                principal_paise: pr,
                rate_percent: rt != null && !Number.isNaN(rt) ? rt : null,
                start_date: fiStart.trim() || null,
                maturity_date: fiMat.trim() || null,
              })
            }}
          >
            <label className="text-xs text-zinc-600">
              Institution
              <input
                className="mt-1 block w-48 rounded border border-zinc-200 px-2 py-1 text-sm"
                value={fiInst}
                onChange={(e) => setFiInst(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Type
              <select
                className="mt-1 block rounded border border-zinc-200 px-2 py-1 text-sm"
                value={fiType}
                onChange={(e) => setFiType(e.target.value)}
              >
                {FIXED_INCOME_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-zinc-600">
              Principal (₹)
              <input
                className="mt-1 block w-28 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={fiPrin}
                onChange={(e) => setFiPrin(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Rate %
              <input
                className="mt-1 block w-20 rounded border border-zinc-200 px-2 py-1 text-right text-sm"
                inputMode="decimal"
                value={fiRate}
                onChange={(e) => setFiRate(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Start
              <input
                type="date"
                className="mt-1 block rounded border border-zinc-200 px-2 py-1 text-sm"
                value={fiStart}
                onChange={(e) => setFiStart(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Maturity
              <input
                type="date"
                className="mt-1 block rounded border border-zinc-200 px-2 py-1 text-sm"
                value={fiMat}
                onChange={(e) => setFiMat(e.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={fi.isPending}
              className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Add
            </button>
          </form>
          {fi.isError ? <p className="mt-2 text-sm text-red-600">{String(fi.error)}</p> : null}
        </Panel>

        <Panel variant="table" padding={false} className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3">Institution</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3 text-right">Principal ₹</th>
                <th className="px-4 py-3 text-right">Rate</th>
                <th className="px-4 py-3">Start</th>
                <th className="px-4 py-3">Maturity</th>
                <th className="px-4 py-3 w-24" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {fiList.data.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-zinc-500">
                    No fixed income rows — add one above
                  </td>
                </tr>
              ) : (
                fiList.data.map((r) => (
                  <FixedIncomeRow
                    key={`${r.id}-${r.institution}-${r.principal_paise}-${r.rate_percent ?? 0}-${r.maturity_date ?? ''}`}
                    r={r}
                    busy={fiUp.isPending || fiDel.isPending}
                    onSave={(body) => fiUp.mutate({ id: r.id, body })}
                    onDelete={() => fiDel.mutate(r.id)}
                  />
                ))
              )}
            </tbody>
          </table>
        </Panel>
        {fiUp.isError ? <p className="mt-2 text-sm text-red-600">{String(fiUp.error)}</p> : null}
      </section>

      <section>
        <SectionTitle>Market holdings</SectionTitle>

        <Panel className="mb-4">
          <h3 className="mb-2 text-sm font-semibold text-zinc-800">Add holding</h3>
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              const u = parseFloat(hiUnits.replace(/,/g, ''))
              const a = rupeesToPaise(hiAvg)
              const c = rupeesToPaise(hiCur)
              if (Number.isNaN(u) || u <= 0 || a == null || c == null) {
                return
              }
              inv.mutate({
                instrument: hiName.trim() || 'Holding',
                type: hiType,
                isin_code: hiIsin.trim() || null,
                units: u,
                avg_price_paise: a,
                current_price_paise: c,
              })
            }}
          >
            <label className="text-xs text-zinc-600">
              Instrument
              <input
                className="mt-1 block w-56 rounded border border-zinc-200 px-2 py-1 text-sm"
                value={hiName}
                onChange={(e) => setHiName(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Type
              <select
                className="mt-1 block rounded border border-zinc-200 px-2 py-1 text-sm"
                value={hiType}
                onChange={(e) => setHiType(e.target.value)}
              >
                {INVESTMENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-zinc-600">
              ISIN
              <input
                className="mt-1 block w-36 rounded border border-zinc-200 px-2 py-1 font-mono text-xs"
                value={hiIsin}
                onChange={(e) => setHiIsin(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Units
              <input
                className="mt-1 block w-24 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={hiUnits}
                onChange={(e) => setHiUnits(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Avg ₹
              <input
                className="mt-1 block w-24 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={hiAvg}
                onChange={(e) => setHiAvg(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-600">
              Price ₹
              <input
                className="mt-1 block w-24 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={hiCur}
                onChange={(e) => setHiCur(e.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={inv.isPending}
              className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Add
            </button>
          </form>
          {inv.isError ? <p className="mt-2 text-sm text-red-600">{String(inv.error)}</p> : null}
        </Panel>

        <Panel variant="table" padding={false} className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3">Instrument</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">ISIN</th>
                <th className="px-4 py-3 text-right">Units</th>
                <th className="px-4 py-3 text-right">Avg ₹</th>
                <th className="px-4 py-3 text-right">Price ₹</th>
                <th className="px-4 py-3 text-right">Cost</th>
                <th className="px-4 py-3 text-right">Value</th>
                <th className="px-4 py-3 text-right">P&L</th>
                <th className="px-4 py-3 w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {holdings.data.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-4 py-6 text-center text-zinc-500">
                    No holdings — add one above
                  </td>
                </tr>
              ) : (
                holdings.data.map((h) => (
                  <HoldingRow
                    key={`${h.id}-${h.instrument}-${h.units}-${h.avg_price_paise}-${h.current_price_paise}`}
                    h={h}
                    busy={invUp.isPending || invDel.isPending}
                    onSave={(body) => invUp.mutate({ id: h.id, body })}
                    onDelete={() => invDel.mutate(h.id)}
                  />
                ))
              )}
            </tbody>
          </table>
        </Panel>
        {invUp.isError ? <p className="mt-2 text-sm text-red-600">{String(invUp.error)}</p> : null}
      </section>

      <section>
        <SectionTitle>SIP projector</SectionTitle>
        <Panel>
        <h2 className="sr-only">SIP projector</h2>
        <p className="mt-1 text-sm text-zinc-600">
          End-of-month contributions; CAGR compounding (illustrative, not advice). Set annual SIP
          step-up to 0 for a flat monthly amount.
        </p>
        <div className="mt-4 flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-sm text-zinc-600">
            Monthly (₹)
            <input
              type="text"
              inputMode="decimal"
              value={sipMonthly}
              onChange={(e) => setSipMonthly(e.target.value)}
              className="w-32 rounded-md border border-zinc-200 px-3 py-2 text-zinc-900"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-zinc-600">
            Annual SIP step-up %
            <input
              type="text"
              inputMode="decimal"
              value={sipStepUp}
              onChange={(e) => setSipStepUp(e.target.value)}
              className="w-28 rounded-md border border-zinc-200 px-3 py-2 text-zinc-900"
              title="0 = flat monthly SIP"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-zinc-600">
            Years
            <input
              type="text"
              inputMode="decimal"
              value={sipYears}
              onChange={(e) => setSipYears(e.target.value)}
              className="w-24 rounded-md border border-zinc-200 px-3 py-2 text-zinc-900"
            />
          </label>
          <label className="flex flex-col gap-1 text-sm text-zinc-600">
            CAGR %
            <input
              type="text"
              inputMode="decimal"
              value={sipCagr}
              onChange={(e) => setSipCagr(e.target.value)}
              className="w-24 rounded-md border border-zinc-200 px-3 py-2 text-zinc-900"
            />
          </label>
          <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm">
            <span className="text-zinc-600">Projected corpus</span>
            <p className="text-lg font-semibold tabular-nums text-emerald-900">
              {sipResult != null ? formatPaise(sipResult) : '—'}
            </p>
          </div>
        </div>
        </Panel>
      </section>
    </div>
  )
}

function FixedIncomeRow({
  r,
  busy,
  onSave,
  onDelete,
}: {
  r: FixedIncomeOut
  busy: boolean
  onSave: (body: {
    institution?: string
    type?: string
    principal_paise?: number
    rate_percent?: number | null
    start_date?: string | null
    maturity_date?: string | null
  }) => void
  onDelete: () => void
}) {
  const [inst, setInst] = useState(r.institution)
  const [t, setT] = useState(r.type)
  const [pr, setPr] = useState(String(r.principal_paise / 100))
  const [rt, setRt] = useState(r.rate_percent != null ? String(r.rate_percent) : '')
  const [sd, setSd] = useState(r.start_date ?? '')
  const [md, setMd] = useState(r.maturity_date ?? '')

  const save = () => {
    const p = rupeesToPaise(pr)
    if (p == null) {
      return
    }
    const rate = rt.trim() === '' ? null : Number.parseFloat(rt)
    onSave({
      institution: inst.trim() || r.institution,
      type: t,
      principal_paise: p,
      rate_percent: rate != null && !Number.isNaN(rate) ? rate : null,
      start_date: sd.trim() || null,
      maturity_date: md.trim() || null,
    })
  }

  return (
    <tr className="hover:bg-zinc-50/80">
      <td className="px-4 py-2">
        <input
          className="w-full min-w-[6rem] rounded border border-zinc-200 px-1 py-0.5 text-sm"
          value={inst}
          onChange={(e) => setInst(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <select
          className="rounded border border-zinc-200 px-1 py-0.5 text-xs"
          value={t}
          onChange={(e) => setT(e.target.value)}
        >
          {FIXED_INCOME_TYPES.map((x) => (
            <option key={x} value={x}>
              {x}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2 text-right">
        <input
          className="w-24 rounded border border-zinc-200 px-1 py-0.5 text-right text-xs tabular-nums"
          inputMode="decimal"
          value={pr}
          onChange={(e) => setPr(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 text-right">
        <input
          className="w-16 rounded border border-zinc-200 px-1 py-0.5 text-right text-xs tabular-nums"
          inputMode="decimal"
          value={rt}
          onChange={(e) => setRt(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <input
          type="date"
          className="rounded border border-zinc-200 px-1 py-0.5 text-xs"
          value={sd}
          onChange={(e) => setSd(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <input
          type="date"
          className="rounded border border-zinc-200 px-1 py-0.5 text-xs"
          value={md}
          onChange={(e) => setMd(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <div className="flex flex-col gap-1">
          <button
            type="button"
            disabled={busy}
            className="text-xs font-medium text-emerald-700 hover:underline disabled:opacity-50"
            onClick={save}
          >
            Save
          </button>
          <button
            type="button"
            disabled={busy}
            className="text-xs text-red-700 hover:underline disabled:opacity-50"
            onClick={() => {
              if (window.confirm('Delete this fixed income row?')) {
                onDelete()
              }
            }}
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}

function HoldingRow({
  h,
  busy,
  onSave,
  onDelete,
}: {
  h: InvestmentOut
  busy: boolean
  onSave: (body: {
    instrument?: string
    type?: string
    isin_code?: string | null
    units?: number | null
    avg_price_paise?: number | null
    current_price_paise?: number | null
  }) => void
  onDelete: () => void
}) {
  const [name, setName] = useState(h.instrument)
  const [type, setType] = useState(h.type)
  const [isin, setIsin] = useState(h.isin_code ?? '')
  const [units, setUnits] = useState(h.units != null ? String(h.units) : '')
  const [avg, setAvg] = useState(h.avg_price_paise != null ? String(h.avg_price_paise / 100) : '')
  const [cur, setCur] = useState(
    h.current_price_paise != null ? String(h.current_price_paise / 100) : '',
  )

  const save = () => {
    const u = parseFloat(units.replace(/,/g, ''))
    const a = avg.trim() === '' ? null : rupeesToPaise(avg)
    const c = cur.trim() === '' ? null : rupeesToPaise(cur)
    if (Number.isNaN(u) || u < 0) {
      return
    }
    if (avg.trim() !== '' && a == null) {
      return
    }
    if (cur.trim() !== '' && c == null) {
      return
    }
    onSave({
      instrument: name.trim() || h.instrument,
      type,
      isin_code: isin.trim() || null,
      units: u,
      avg_price_paise: a,
      current_price_paise: c,
    })
  }

  return (
    <tr className="hover:bg-zinc-50/80">
      <td className="px-4 py-2">
        <input
          className="w-full min-w-[7rem] rounded border border-zinc-200 px-1 py-0.5 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <select
          className="rounded border border-zinc-200 px-1 py-0.5 text-xs"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          {INVESTMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2">
        <input
          className="w-24 rounded border border-zinc-200 px-1 py-0.5 font-mono text-[10px]"
          value={isin}
          onChange={(e) => setIsin(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 text-right">
        <input
          className="w-24 rounded border border-zinc-200 px-1 py-0.5 text-right text-xs tabular-nums"
          inputMode="decimal"
          value={units}
          onChange={(e) => setUnits(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 text-right">
        <input
          className="w-20 rounded border border-zinc-200 px-1 py-0.5 text-right text-xs tabular-nums"
          inputMode="decimal"
          value={avg}
          onChange={(e) => setAvg(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 text-right">
        <input
          className="w-20 rounded border border-zinc-200 px-1 py-0.5 text-right text-xs tabular-nums"
          inputMode="decimal"
          value={cur}
          onChange={(e) => setCur(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 text-right tabular-nums text-zinc-700">
        {h.cost_basis_paise != null ? formatPaise(h.cost_basis_paise) : '—'}
      </td>
      <td className="px-4 py-2 text-right tabular-nums text-zinc-900">
        {h.market_value_paise != null ? formatPaise(h.market_value_paise) : '—'}
      </td>
      <td
        className={`px-4 py-2 text-right tabular-nums ${
          (h.unrealized_paise ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-700'
        }`}
      >
        {h.unrealized_paise != null ? formatPaise(h.unrealized_paise) : '—'}
      </td>
      <td className="px-4 py-2">
        <div className="flex flex-col gap-1">
          <button
            type="button"
            disabled={busy}
            className="text-xs font-medium text-emerald-700 hover:underline disabled:opacity-50"
            onClick={save}
          >
            Save
          </button>
          <button
            type="button"
            disabled={busy}
            className="text-xs text-red-700 hover:underline disabled:opacity-50"
            onClick={() => {
              if (window.confirm('Delete this holding?')) {
                onDelete()
              }
            }}
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}
