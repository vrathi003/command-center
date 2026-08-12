import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { deleteGoal, fetchGoals, postGoal, putGoal } from '@/lib/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'
import type { GoalOut } from '@/types/api'

function rupeesInputToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) {
    return null
  }
  return Math.round(n * 100)
}

function paiseToRupeesInput(paise: number): string {
  return String(paise / 100)
}

/** Corpus at retirement: existing savings grow annually + monthly SIP to month-end. */
function retirementCorpusPaise(
  currentAge: number,
  retireAge: number,
  currentCorpusPaise: number,
  monthlyContribPaise: number,
  annualReturnPercent: number,
): number {
  const years = Math.max(0, retireAge - currentAge)
  const n = Math.max(0, Math.floor(years * 12))
  const rm = annualReturnPercent / 100 / 12
  const fvPv = currentCorpusPaise * (1 + annualReturnPercent / 100) ** years
  let fvSip = 0
  if (n > 0) {
    if (rm <= 0) {
      fvSip = monthlyContribPaise * n
    } else {
      fvSip = monthlyContribPaise * ((Math.pow(1 + rm, n) - 1) / rm)
    }
  }
  return Math.round(fvPv + fvSip)
}

const RETIREMENT_CORPUS_STORAGE_KEY = 'pfos:goals:retirement-corpus-inputs'
const EMERGENCY_EXPENSES_STORAGE_KEY = 'pfos:goals:emergency-monthly-expenses'

type RetirementCorpusInputs = {
  retCurAge: string
  retAge: string
  retCorpus: string
  retMonthly: string
  retReturn: string
}

const DEFAULT_RETIREMENT_INPUTS: RetirementCorpusInputs = {
  retCurAge: '35',
  retAge: '60',
  retCorpus: '500000',
  retMonthly: '25000',
  retReturn: '10',
}

function loadRetirementCorpusInputs(): RetirementCorpusInputs {
  if (typeof window === 'undefined') {
    return DEFAULT_RETIREMENT_INPUTS
  }
  try {
    const raw = window.localStorage.getItem(RETIREMENT_CORPUS_STORAGE_KEY)
    if (!raw) {
      return DEFAULT_RETIREMENT_INPUTS
    }
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') {
      return DEFAULT_RETIREMENT_INPUTS
    }
    const o = parsed as Record<string, unknown>
    const str = (k: keyof RetirementCorpusInputs) =>
      typeof o[k] === 'string' ? (o[k] as string) : DEFAULT_RETIREMENT_INPUTS[k]
    return {
      retCurAge: str('retCurAge'),
      retAge: str('retAge'),
      retCorpus: str('retCorpus'),
      retMonthly: str('retMonthly'),
      retReturn: str('retReturn'),
    }
  } catch {
    return DEFAULT_RETIREMENT_INPUTS
  }
}

function loadEmergencyMonthlyExpenses(): string {
  if (typeof window === 'undefined') {
    return '50000'
  }
  try {
    return window.localStorage.getItem(EMERGENCY_EXPENSES_STORAGE_KEY) ?? '50000'
  } catch {
    return '50000'
  }
}

function isEmergencyGoal(goal: GoalOut): boolean {
  const hay = `${goal.name} ${goal.category ?? ''}`.toLowerCase()
  return hay.includes('emergency')
}

function monthsUntil(targetDate: string): number | null {
  const end = new Date(`${targetDate}T00:00:00`)
  if (Number.isNaN(end.getTime())) {
    return null
  }
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const ms = end.getTime() - start.getTime()
  if (ms <= 0) {
    return 0
  }
  return Math.max(1, Math.ceil(ms / (1000 * 60 * 60 * 24 * 30.4375)))
}

function remainingPaise(goal: GoalOut): number {
  return Math.max(0, goal.target_amount_paise - goal.current_amount_paise)
}

function monthsToGoal(goal: GoalOut): number | null {
  const monthly = goal.monthly_contribution_paise ?? 0
  const rem = remainingPaise(goal)
  if (rem <= 0) {
    return 0
  }
  if (monthly <= 0) {
    return null
  }
  return Math.ceil(rem / monthly)
}

type TrackStatus = 'done' | 'on_track' | 'behind' | 'unknown'

function trackStatus(goal: GoalOut): TrackStatus {
  const rem = remainingPaise(goal)
  if (rem <= 0) {
    return 'done'
  }
  const monthly = goal.monthly_contribution_paise ?? 0
  if (!goal.target_date || monthly <= 0) {
    return 'unknown'
  }
  const monthsLeft = monthsUntil(goal.target_date)
  if (monthsLeft == null) {
    return 'unknown'
  }
  if (monthsLeft <= 0) {
    return 'behind'
  }
  const required = Math.ceil(rem / monthsLeft)
  return monthly >= required ? 'on_track' : 'behind'
}

function goalsPortfolio(goals: GoalOut[]) {
  let totalTarget = 0
  let totalSaved = 0
  let monthlySave = 0
  let onTrack = 0
  let trackable = 0

  for (const g of goals) {
    totalTarget += g.target_amount_paise
    totalSaved += g.current_amount_paise
    monthlySave += g.monthly_contribution_paise ?? 0
    const status = trackStatus(g)
    if (status === 'on_track' || status === 'done') {
      onTrack += 1
      trackable += 1
    } else if (status === 'behind') {
      trackable += 1
    }
  }

  const overallPct =
    totalTarget > 0 ? Math.min(100, (totalSaved / totalTarget) * 100) : null

  return { totalTarget, totalSaved, monthlySave, onTrack, trackable, overallPct, count: goals.length }
}

export function GoalsPage() {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['goals'],
    queryFn: fetchGoals,
  })

  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [targetRupees, setTargetRupees] = useState('500000')
  const [currentRupees, setCurrentRupees] = useState('0')
  const [contribRupees, setContribRupees] = useState('')
  const [targetDate, setTargetDate] = useState('')

  const [retirement, setRetirement] = useState<RetirementCorpusInputs>(() => loadRetirementCorpusInputs())
  const [emergencyMonthly, setEmergencyMonthly] = useState(() => loadEmergencyMonthlyExpenses())

  useEffect(() => {
    try {
      window.localStorage.setItem(RETIREMENT_CORPUS_STORAGE_KEY, JSON.stringify(retirement))
    } catch {
      // ignore quota / private mode
    }
  }, [retirement])

  useEffect(() => {
    try {
      window.localStorage.setItem(EMERGENCY_EXPENSES_STORAGE_KEY, emergencyMonthly)
    } catch {
      // ignore
    }
  }, [emergencyMonthly])

  const ca = Number.parseInt(retirement.retCurAge, 10)
  const ra = Number.parseInt(retirement.retAge, 10)
  const retCorpus = rupeesInputToPaise(retirement.retCorpus)
  const retMonthly = rupeesInputToPaise(retirement.retMonthly)
  const retReturn = Number.parseFloat(retirement.retReturn)
  const retirementFv =
    !Number.isNaN(ca) &&
    !Number.isNaN(ra) &&
    ra > ca &&
    retCorpus != null &&
    retMonthly != null &&
    !Number.isNaN(retReturn)
      ? retirementCorpusPaise(ca, ra, retCorpus, retMonthly, retReturn)
      : null

  const create = useMutation({
    mutationFn: postGoal,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['goals'] }),
  })

  const remove = useMutation({
    mutationFn: deleteGoal,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['goals'] }),
  })

  const update = useMutation({
    mutationFn: (args: {
      id: number
      name: string
      category: string | null
      target_amount_paise: number
      current_amount_paise: number
      monthly_contribution_paise: number | null
      target_date: string | null
    }) => {
      const { id, ...body } = args
      return putGoal(id, body)
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['goals'] }),
  })

  if (q.isPending) {
    return <PageLoading lines={3} showFooterBlock />
  }

  if (q.isError) {
    return (
      <PageError title="Could not load goals" message={<p className="text-sm">{String(q.error)}</p>} />
    )
  }

  const rows = q.data ?? []
  const totals = goalsPortfolio(rows)
  const emergencyGoal = rows.find(isEmergencyGoal) ?? null
  const emergencyMonthlyPaise = rupeesInputToPaise(emergencyMonthly)
  const emergencyTargetPaise =
    emergencyMonthlyPaise != null ? emergencyMonthlyPaise * 6 : null
  const emergencySaved = emergencyGoal?.current_amount_paise ?? 0
  const emergencyGap =
    emergencyTargetPaise != null ? Math.max(0, emergencyTargetPaise - emergencySaved) : null

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Targets"
        title="Goals"
        description="Savings targets, time-to-goal, and retirement planning · refreshes every 30s"
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <KpiCard tone="neutral" label="Goals" value={String(totals.count)} />
        <KpiCard
          tone="balance"
          label="Total target"
          value={formatPaiseCompact(totals.totalTarget)}
        />
        <KpiCard
          tone="spending"
          label="Total saved"
          value={formatPaiseCompact(totals.totalSaved)}
        />
        <KpiCard
          tone="neutral"
          label="Overall progress"
          value={totals.overallPct != null ? `${totals.overallPct.toFixed(0)}%` : '—'}
        />
        <KpiCard
          tone="balance"
          label="Monthly save"
          value={formatPaiseCompact(totals.monthlySave)}
          hint="Sum of planned contributions"
        />
        <KpiCard
          tone={totals.trackable > 0 && totals.onTrack === totals.trackable ? 'spending' : 'neutral'}
          label="On track"
          value={totals.trackable > 0 ? `${totals.onTrack}/${totals.trackable}` : '—'}
          hint="Needs target date + monthly save"
        />
      </section>

      <section>
        <SectionTitle>Emergency fund</SectionTitle>
        <Panel>
          <p className="mb-4 text-sm text-zinc-600">
            Target = <span className="font-medium text-zinc-800">6 × monthly expenses</span> you
            enter below. Not linked to ledger spend.
          </p>
          <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end">
            <label className="text-xs font-medium text-zinc-700">
              Monthly expenses (₹)
              <input
                className="mt-1 block h-10 w-36 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={emergencyMonthly}
                onChange={(e) => setEmergencyMonthly(e.target.value)}
              />
            </label>
            <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-zinc-50 px-3 py-2.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  Target (6×)
                </p>
                <p className="mt-1 text-sm font-semibold tabular-nums text-zinc-900">
                  {emergencyTargetPaise != null ? formatPaiseCompact(emergencyTargetPaise) : '—'}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-50 px-3 py-2.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  Saved
                </p>
                <p className="mt-1 text-sm font-semibold tabular-nums text-zinc-900">
                  {emergencyGoal ? formatPaiseCompact(emergencySaved) : '—'}
                </p>
              </div>
              <div className="rounded-xl bg-zinc-50 px-3 py-2.5">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Gap</p>
                <p className="mt-1 text-sm font-semibold tabular-nums text-zinc-900">
                  {emergencyGap != null && emergencyGoal ? formatPaiseCompact(emergencyGap) : '—'}
                </p>
              </div>
            </div>
            <button
              type="button"
              disabled={create.isPending || update.isPending || emergencyTargetPaise == null}
              className="h-10 rounded-lg bg-emerald-700 px-4 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-50"
              onClick={() => {
                if (emergencyTargetPaise == null) {
                  return
                }
                if (emergencyGoal) {
                  update.mutate({
                    id: emergencyGoal.id,
                    name: emergencyGoal.name,
                    category: emergencyGoal.category ?? 'Emergency',
                    target_amount_paise: emergencyTargetPaise,
                    current_amount_paise: emergencyGoal.current_amount_paise,
                    monthly_contribution_paise: emergencyGoal.monthly_contribution_paise,
                    target_date: emergencyGoal.target_date,
                  })
                } else {
                  create.mutate({
                    name: 'Emergency fund',
                    category: 'Emergency',
                    target_amount_paise: emergencyTargetPaise,
                    current_amount_paise: 0,
                    monthly_contribution_paise: null,
                    target_date: null,
                  })
                }
              }}
            >
              {emergencyGoal ? 'Update emergency goal target' : 'Create emergency goal'}
            </button>
          </div>
        </Panel>
      </section>

      <section>
        <SectionTitle>Retirement corpus (illustrative)</SectionTitle>
        <Panel variant="emerald">
          <p className="mb-4 text-xs text-zinc-500">
            Projects today&apos;s corpus and a steady monthly contribution with a flat annual return
            until retirement age. Not advice — ignores taxes, inflation, and income changes.
          </p>
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col text-xs font-medium text-zinc-600">
              Current age
              <input
                className="mt-1 h-10 w-20 rounded-lg border border-zinc-200 bg-white px-2 text-sm tabular-nums shadow-sm"
                inputMode="numeric"
                value={retirement.retCurAge}
                onChange={(e) => setRetirement((prev) => ({ ...prev, retCurAge: e.target.value }))}
              />
            </label>
            <label className="flex flex-col text-xs font-medium text-zinc-600">
              Retire at
              <input
                className="mt-1 h-10 w-20 rounded-lg border border-zinc-200 bg-white px-2 text-sm tabular-nums shadow-sm"
                inputMode="numeric"
                value={retirement.retAge}
                onChange={(e) => setRetirement((prev) => ({ ...prev, retAge: e.target.value }))}
              />
            </label>
            <label className="flex flex-col text-xs font-medium text-zinc-600">
              Current corpus (₹)
              <input
                className="mt-1 h-10 w-32 rounded-lg border border-zinc-200 bg-white px-2 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={retirement.retCorpus}
                onChange={(e) => setRetirement((prev) => ({ ...prev, retCorpus: e.target.value }))}
              />
            </label>
            <label className="flex flex-col text-xs font-medium text-zinc-600">
              Monthly invest (₹)
              <input
                className="mt-1 h-10 w-32 rounded-lg border border-zinc-200 bg-white px-2 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={retirement.retMonthly}
                onChange={(e) => setRetirement((prev) => ({ ...prev, retMonthly: e.target.value }))}
              />
            </label>
            <label className="flex flex-col text-xs font-medium text-zinc-600">
              Return % (nominal, annual)
              <input
                className="mt-1 h-10 w-24 rounded-lg border border-zinc-200 bg-white px-2 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={retirement.retReturn}
                onChange={(e) => setRetirement((prev) => ({ ...prev, retReturn: e.target.value }))}
              />
            </label>
            <div className="rounded-xl bg-emerald-50 px-4 py-3 text-sm ring-1 ring-emerald-900/5">
              <span className="text-zinc-600">Projected at retirement</span>
              <p className="text-lg font-semibold tabular-nums text-emerald-900">
                {retirementFv != null ? formatPaise(retirementFv) : '—'}
              </p>
            </div>
          </div>
        </Panel>
      </section>

      <section>
        <SectionTitle>Add goal</SectionTitle>
        <Panel variant="emerald">
          <form
            className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end"
            onSubmit={(e) => {
              e.preventDefault()
              const t = rupeesInputToPaise(targetRupees)
              const c = rupeesInputToPaise(currentRupees)
              if (t == null || c == null) {
                return
              }
              const m = contribRupees.trim() === '' ? null : rupeesInputToPaise(contribRupees)
              if (contribRupees.trim() !== '' && m == null) {
                return
              }
              create.mutate({
                name: name.trim() || 'Goal',
                category: category.trim() || null,
                target_amount_paise: t,
                current_amount_paise: c,
                monthly_contribution_paise: m,
                target_date: targetDate.trim() || null,
              })
              setName('')
              setCategory('')
              setContribRupees('')
              setTargetDate('')
              setCurrentRupees('0')
            }}
          >
            <label className="text-xs font-medium text-zinc-700">
              Name
              <input
                className="mt-1 block h-10 min-w-[10rem] rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="House down payment"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Category
              <input
                className="mt-1 block h-10 w-36 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Travel"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Target (₹)
              <input
                className="mt-1 block h-10 w-32 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={targetRupees}
                onChange={(e) => setTargetRupees(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Current (₹)
              <input
                className="mt-1 block h-10 w-32 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={currentRupees}
                onChange={(e) => setCurrentRupees(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Monthly save (₹)
              <input
                className="mt-1 block h-10 w-32 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={contribRupees}
                onChange={(e) => setContribRupees(e.target.value)}
                placeholder="optional"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Target date
              <input
                type="date"
                className="mt-1 block h-10 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={targetDate}
                onChange={(e) => setTargetDate(e.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={create.isPending}
              className="h-10 rounded-lg bg-emerald-700 px-5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-50"
            >
              Add goal
            </button>
          </form>
          {create.isError ? <p className="mt-3 text-sm text-red-600">{String(create.error)}</p> : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Your goals</SectionTitle>
        {rows.length === 0 ? (
          <Panel className="text-center text-sm text-zinc-600">No goals yet — add one above.</Panel>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((g) => (
              <GoalCard
                key={g.id}
                goal={g}
                busy={update.isPending || remove.isPending}
                onSave={(body) => update.mutate({ id: g.id, ...body })}
                onDelete={() => {
                  if (window.confirm(`Delete goal "${g.name}"?`)) {
                    remove.mutate(g.id)
                  }
                }}
              />
            ))}
          </div>
        )}
        {remove.isError ? <p className="mt-2 text-sm text-red-600">{String(remove.error)}</p> : null}
        {update.isError ? <p className="mt-2 text-sm text-red-600">{String(update.error)}</p> : null}
      </section>
    </div>
  )
}

function trackBadge(status: TrackStatus): { label: string; className: string } {
  switch (status) {
    case 'done':
      return { label: 'Complete', className: 'bg-emerald-100 text-emerald-800' }
    case 'on_track':
      return { label: 'On track', className: 'bg-sky-100 text-sky-800' }
    case 'behind':
      return { label: 'Behind', className: 'bg-amber-100 text-amber-900' }
    default:
      return { label: 'No pace yet', className: 'bg-zinc-100 text-zinc-600' }
  }
}

function GoalCard({
  goal,
  onSave,
  onDelete,
  busy,
}: {
  goal: GoalOut
  onSave: (body: {
    name: string
    category: string | null
    target_amount_paise: number
    current_amount_paise: number
    monthly_contribution_paise: number | null
    target_date: string | null
  }) => void
  onDelete: () => void
  busy: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(goal.name)
  const [cat, setCat] = useState(goal.category ?? '')
  const [targetRupees, setTargetRupees] = useState(paiseToRupeesInput(goal.target_amount_paise))
  const [curRupees, setCurRupees] = useState(paiseToRupeesInput(goal.current_amount_paise))
  const [contribRupees, setContribRupees] = useState(
    goal.monthly_contribution_paise != null ? paiseToRupeesInput(goal.monthly_contribution_paise) : '',
  )
  const [td, setTd] = useState(goal.target_date ?? '')

  useEffect(() => {
    setName(goal.name)
    setCat(goal.category ?? '')
    setTargetRupees(paiseToRupeesInput(goal.target_amount_paise))
    setCurRupees(paiseToRupeesInput(goal.current_amount_paise))
    setContribRupees(
      goal.monthly_contribution_paise != null
        ? paiseToRupeesInput(goal.monthly_contribution_paise)
        : '',
    )
    setTd(goal.target_date ?? '')
  }, [goal])

  const status = trackStatus(goal)
  const badge = trackBadge(status)
  const etaMonths = monthsToGoal(goal)
  const progress = goal.progress_pct ?? 0

  return (
    <div className="flex flex-col rounded-2xl border border-zinc-200/80 bg-white p-5 shadow-md shadow-zinc-900/5 ring-1 ring-zinc-900/[0.04]">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-zinc-900">{goal.name}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {goal.category ? (
              <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-700">
                {goal.category}
              </span>
            ) : null}
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${badge.className}`}>
              {badge.label}
            </span>
          </div>
        </div>
        <span className="shrink-0 text-sm font-semibold tabular-nums text-zinc-800">
          {progress.toFixed(0)}%
        </span>
      </div>

      <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-zinc-100">
        <div
          className="h-full rounded-full bg-emerald-600 transition-all"
          style={{ width: `${Math.min(100, progress)}%` }}
        />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-zinc-500">Saved</p>
          <p className="font-semibold tabular-nums text-zinc-900">
            {formatPaiseCompact(goal.current_amount_paise)}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Target</p>
          <p className="font-semibold tabular-nums text-zinc-900">
            {formatPaiseCompact(goal.target_amount_paise)}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Monthly save</p>
          <p className="tabular-nums text-zinc-800">
            {goal.monthly_contribution_paise != null
              ? formatPaiseCompact(goal.monthly_contribution_paise)
              : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Time to goal</p>
          <p className="tabular-nums text-zinc-800">
            {etaMonths == null ? '—' : etaMonths === 0 ? 'Done' : `~${etaMonths} mo`}
          </p>
        </div>
        {goal.target_date ? (
          <div className="col-span-2">
            <p className="text-xs text-zinc-500">Target date</p>
            <p className="text-zinc-800">{goal.target_date}</p>
          </div>
        ) : null}
      </div>

      {editing ? (
        <div className="mt-4 space-y-2 border-t border-zinc-100 pt-4">
          <input
            className="h-9 w-full rounded-lg border border-zinc-200 px-2 text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Name"
          />
          <input
            className="h-9 w-full rounded-lg border border-zinc-200 px-2 text-sm"
            value={cat}
            onChange={(e) => setCat(e.target.value)}
            placeholder="Category"
          />
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-zinc-500">
              Current (₹)
              <input
                className="mt-1 h-9 w-full rounded-lg border border-zinc-200 px-2 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={curRupees}
                onChange={(e) => setCurRupees(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-500">
              Target (₹)
              <input
                className="mt-1 h-9 w-full rounded-lg border border-zinc-200 px-2 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={targetRupees}
                onChange={(e) => setTargetRupees(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-500">
              Monthly (₹)
              <input
                className="mt-1 h-9 w-full rounded-lg border border-zinc-200 px-2 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={contribRupees}
                onChange={(e) => setContribRupees(e.target.value)}
              />
            </label>
            <label className="text-xs text-zinc-500">
              Date
              <input
                type="date"
                className="mt-1 h-9 w-full rounded-lg border border-zinc-200 px-2 text-sm"
                value={td}
                onChange={(e) => setTd(e.target.value)}
              />
            </label>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              className="h-9 flex-1 rounded-lg bg-emerald-700 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
              onClick={() => {
                const t = rupeesInputToPaise(targetRupees)
                const c = rupeesInputToPaise(curRupees)
                if (t == null || c == null) {
                  return
                }
                const m = contribRupees.trim() === '' ? null : rupeesInputToPaise(contribRupees)
                if (contribRupees.trim() !== '' && m == null) {
                  return
                }
                onSave({
                  name: name.trim() || goal.name,
                  category: cat.trim() || null,
                  target_amount_paise: t,
                  current_amount_paise: c,
                  monthly_contribution_paise: m,
                  target_date: td.trim() || null,
                })
                setEditing(false)
              }}
            >
              Save
            </button>
            <button
              type="button"
              className="h-9 rounded-lg border border-zinc-200 px-3 text-sm text-zinc-700 hover:bg-zinc-50"
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex gap-2 border-t border-zinc-100 pt-4">
          <button
            type="button"
            className="h-9 flex-1 rounded-lg border border-zinc-200 text-sm font-medium text-zinc-800 hover:bg-zinc-50"
            onClick={() => setEditing(true)}
          >
            Edit
          </button>
          <button
            type="button"
            disabled={busy}
            className="h-9 rounded-lg border border-red-200 px-3 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
            onClick={onDelete}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  )
}
