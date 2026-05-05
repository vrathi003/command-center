import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { deleteGoal, fetchGoals, postGoal, putGoal } from '@/lib/api'
import { formatPaise } from '@/lib/format'
import type { GoalOut } from '@/types/api'


function rupeesInputToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) {
    return null
  }
  return Math.round(n * 100)
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

  useEffect(() => {
    try {
      window.localStorage.setItem(RETIREMENT_CORPUS_STORAGE_KEY, JSON.stringify(retirement))
    } catch {
      // ignore quota / private mode
    }
  }, [retirement])

  const retirementFv = useMemo(() => {
    const ca = Number.parseInt(retirement.retCurAge, 10)
    const ra = Number.parseInt(retirement.retAge, 10)
    const c = rupeesInputToPaise(retirement.retCorpus)
    const m = rupeesInputToPaise(retirement.retMonthly)
    const r = Number.parseFloat(retirement.retReturn)
    if (Number.isNaN(ca) || Number.isNaN(ra) || c == null || m == null || Number.isNaN(r)) {
      return null
    }
    if (ra <= ca) {
      return null
    }
    return retirementCorpusPaise(ca, ra, c, m, r)
  }, [retirement])

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

  const rows = q.data

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Targets"
        title="Goals"
        description="Savings targets · refreshes every 30s"
      />

      <section>
        <SectionTitle>Add goal</SectionTitle>
        <Panel>
        <h2 className="sr-only">Add goal</h2>
        <form
          className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
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
          }}
        >
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Name
            <input
              className="mt-1 rounded-md border border-zinc-200 px-2 py-1.5 text-sm text-zinc-900"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Emergency fund"
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Category
            <input
              className="mt-1 w-36 rounded-md border border-zinc-200 px-2 py-1.5 text-sm text-zinc-900"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Target (₹)
            <input
              className="mt-1 w-28 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={targetRupees}
              onChange={(e) => setTargetRupees(e.target.value)}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Current (₹)
            <input
              className="mt-1 w-28 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={currentRupees}
              onChange={(e) => setCurrentRupees(e.target.value)}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Monthly save (₹)
            <input
              className="mt-1 w-28 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={contribRupees}
              onChange={(e) => setContribRupees(e.target.value)}
              placeholder="optional"
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Target date
            <input
              type="date"
              className="mt-1 rounded-md border border-zinc-200 px-2 py-1.5 text-sm text-zinc-900"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
            />
          </label>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            Add
          </button>
        </form>
        {create.isError ? <p className="mt-2 text-sm text-red-700">{String(create.error)}</p> : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Retirement corpus (illustrative)</SectionTitle>
        <Panel variant="emerald">
        <h2 className="sr-only">Retirement corpus (illustrative)</h2>
        <p className="mb-4 text-xs text-zinc-500">
          Projects today&apos;s corpus and a steady monthly contribution with a flat annual return until
          retirement age. Not advice — ignores taxes, inflation, and income changes.
        </p>
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Current age
            <input
              className="mt-1 w-20 rounded-md border border-zinc-200 px-2 py-1.5 text-sm tabular-nums"
              inputMode="numeric"
              value={retirement.retCurAge}
              onChange={(e) => setRetirement((prev) => ({ ...prev, retCurAge: e.target.value }))}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Retire at
            <input
              className="mt-1 w-20 rounded-md border border-zinc-200 px-2 py-1.5 text-sm tabular-nums"
              inputMode="numeric"
              value={retirement.retAge}
              onChange={(e) => setRetirement((prev) => ({ ...prev, retAge: e.target.value }))}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Current corpus (₹)
            <input
              className="mt-1 w-32 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={retirement.retCorpus}
              onChange={(e) => setRetirement((prev) => ({ ...prev, retCorpus: e.target.value }))}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Monthly invest (₹)
            <input
              className="mt-1 w-32 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={retirement.retMonthly}
              onChange={(e) => setRetirement((prev) => ({ ...prev, retMonthly: e.target.value }))}
            />
          </label>
          <label className="flex flex-col text-xs font-medium text-zinc-600">
            Return % (nominal, annual)
            <input
              className="mt-1 w-24 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
              inputMode="decimal"
              value={retirement.retReturn}
              onChange={(e) => setRetirement((prev) => ({ ...prev, retReturn: e.target.value }))}
            />
          </label>
          <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm">
            <span className="text-zinc-600">Projected at retirement</span>
            <p className="text-lg font-semibold tabular-nums text-emerald-900">
              {retirementFv != null ? formatPaise(retirementFv) : '—'}
            </p>
          </div>
        </div>
        </Panel>
      </section>

      <section>
        <SectionTitle>Your goals</SectionTitle>
        <Panel variant="table" padding={false}>
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="bg-zinc-50 text-xs font-medium uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">Progress</th>
              <th className="px-4 py-2 text-right">Current</th>
              <th className="px-4 py-2 text-right">Target</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <GoalRowEditor
                key={g.id}
                goal={g}
                onSave={(body) => update.mutate({ id: g.id, ...body })}
                onDelete={() => remove.mutate(g.id)}
                busy={update.isPending || remove.isPending}
              />
            ))}
          </tbody>
        </table>
        {rows.length === 0 ? (
          <p className="p-6 text-center text-sm text-zinc-500">No goals yet — add one above.</p>
        ) : null}
        </Panel>
      </section>
    </div>
  )
}

function GoalRowEditor({
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
  const [name, setName] = useState(goal.name)
  const [cat, setCat] = useState(goal.category ?? '')
  const [targetRupees, setTargetRupees] = useState(String(goal.target_amount_paise / 100))
  const [curRupees, setCurRupees] = useState(String(goal.current_amount_paise / 100))
  const [contribRupees, setContribRupees] = useState(
    goal.monthly_contribution_paise != null ? String(goal.monthly_contribution_paise / 100) : '',
  )
  const [td, setTd] = useState(goal.target_date ?? '')

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
        <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-100">
          <div
            className="h-full rounded-full bg-emerald-600"
            style={{ width: `${Math.min(100, goal.progress_pct ?? 0)}%` }}
          />
        </div>
        <p className="mt-1 text-xs text-zinc-500">
          {goal.progress_pct != null ? `${goal.progress_pct.toFixed(0)}%` : '—'}
        </p>
      </td>
      <td className="px-4 py-2 text-right align-top">
        <input
          className="w-24 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
          inputMode="decimal"
          value={curRupees}
          onChange={(e) => setCurRupees(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 text-right align-top">
        <input
          className="w-24 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
          inputMode="decimal"
          value={targetRupees}
          onChange={(e) => setTargetRupees(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 align-top">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            className="rounded border border-zinc-200 px-2 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-50"
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
            }}
          >
            Save
          </button>
          <input
            type="date"
            className="rounded border border-zinc-200 px-1 py-1 text-xs"
            value={td}
            onChange={(e) => setTd(e.target.value)}
          />
          <button
            type="button"
            disabled={busy}
            className="rounded border border-red-200 px-2 py-1 text-xs text-red-800 hover:bg-red-50 disabled:opacity-50"
            onClick={() => {
              if (window.confirm('Delete this goal?')) {
                onDelete()
              }
            }}
          >
            Delete
          </button>
        </div>
        <input
          className="mt-2 w-full rounded border border-zinc-200 px-2 py-1 text-xs"
          placeholder="Category"
          value={cat}
          onChange={(e) => setCat(e.target.value)}
        />
        <label className="mt-1 block text-xs text-zinc-500">
          Monthly save (₹)
          <input
            className="ml-1 w-20 rounded border border-zinc-200 px-1 py-0.5 text-right tabular-nums"
            inputMode="decimal"
            value={contribRupees}
            onChange={(e) => setContribRupees(e.target.value)}
          />
        </label>
      </td>
    </tr>
  )
}
