import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useState } from 'react'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  deleteBudgetCategory,
  fetchBudgetVsActual,
  putBudgetCategory,
  renameBudgetCategory,
} from '@/lib/api'
import { formatPaise } from '@/lib/format'
import type { BudgetVsActualRow } from '@/types/api'


function monthValue(y: number, m: number): string {
  return `${y}-${String(m).padStart(2, '0')}`
}

function parseMonthValue(s: string): { year: number; month: number } {
  const [ys, ms] = s.split('-')
  return { year: Number(ys), month: Number(ms) }
}

function statusStyles(status: BudgetVsActualRow['status']): string {
  switch (status) {
    case 'ok':
      return 'border border-emerald-200/80 bg-emerald-50 text-emerald-900'
    case 'full':
      return 'border border-sky-200/80 bg-sky-50 text-sky-950'
    case 'warn':
      return 'border border-amber-200/80 bg-amber-50 text-amber-950'
    case 'over':
      return 'border border-red-200/80 bg-red-50 text-red-900'
    default:
      return 'border border-zinc-200/80 bg-zinc-50 text-zinc-500'
  }
}

function statusLabel(status: BudgetVsActualRow['status']): string {
  switch (status) {
    case 'ok':
      return 'On track'
    case 'full':
      return 'Fully budgeted'
    case 'warn':
      return 'At risk'
    case 'over':
      return 'Over budget'
    default:
      return 'No cap'
  }
}

function EditableCategoryName({
  category,
  disabled,
  onRename,
}: {
  category: string
  disabled: boolean
  onRename: (next: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(category)

  const commit = useCallback(async () => {
    const t = val.trim()
    if (!t || t === category) {
      setVal(category)
      setEditing(false)
      return
    }
    try {
      await onRename(t)
      setEditing(false)
    } catch {
      /* keep editing; error surfaced by mutation */
    }
  }, [val, category, onRename])

  const cancel = useCallback(() => {
    setVal(category)
    setEditing(false)
  }, [category])

  if (editing) {
    return (
      <input
        autoFocus
        type="text"
        disabled={disabled}
        className="w-full min-w-0 max-w-[14rem] rounded-md border border-emerald-500 bg-white px-2 py-1 text-sm font-medium text-zinc-900 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            void commit()
          }
          if (e.key === 'Escape') {
            e.preventDefault()
            cancel()
          }
        }}
        aria-label="Rename category"
      />
    )
  }

  return (
    <span
      role="button"
      tabIndex={disabled ? -1 : 0}
      className={
        disabled
          ? 'font-medium text-zinc-900'
          : 'cursor-pointer font-medium text-zinc-900 transition-colors hover:text-emerald-800'
      }
      title={disabled ? undefined : 'Double-click to rename'}
      onDoubleClick={() => {
        if (!disabled) {
          setVal(category)
          setEditing(true)
        }
      }}
      onKeyDown={(e) => {
        if (disabled) {
          return
        }
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          setVal(category)
          setEditing(true)
        }
      }}
    >
      {category}
    </span>
  )
}

function BudgetInput({
  category,
  budgetPaise,
  onSave,
  disabled,
}: {
  category: string
  budgetPaise: number | null
  onSave: (paise: number) => void
  disabled: boolean
}) {
  const rupees = (budgetPaise ?? 0) / 100
  const [val, setVal] = useState(String(rupees))

  const sync = useCallback(() => {
    const n = Number.parseFloat(val.replace(/,/g, ''))
    if (Number.isNaN(n) || n < 0) {
      setVal(String(rupees))
      return
    }
    onSave(Math.round(n * 100))
  }, [val, rupees, onSave])

  return (
    <input
      type="text"
      inputMode="decimal"
      disabled={disabled}
      className="h-9 w-full min-w-[6.5rem] max-w-[9rem] rounded-lg border border-zinc-200/90 bg-zinc-50/50 px-3 text-right text-sm font-medium tabular-nums text-zinc-900 shadow-sm transition-colors placeholder:text-zinc-400 focus:border-emerald-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/20 disabled:opacity-50"
      value={val}
      onChange={(e) => setVal(e.target.value)}
      onBlur={sync}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
      }}
      aria-label={`Monthly budget for ${category}`}
    />
  )
}

export function BudgetPage() {
  const qc = useQueryClient()
  const now = useMemo(() => new Date(), [])
  const [ym, setYm] = useState(() => monthValue(now.getFullYear(), now.getMonth() + 1))
  const { year, month } = parseMonthValue(ym)

  const q = useQuery({
    queryKey: ['budget-vs', year, month],
    queryFn: () => fetchBudgetVsActual(year, month),
  })

  const mutation = useMutation({
    mutationFn: ({ category, paise }: { category: string; paise: number }) =>
      putBudgetCategory(category, paise),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const [newCat, setNewCat] = useState('')
  const [newAmt, setNewAmt] = useState('')
  /** When true, hide categories with no monthly cap and zero spend in the selected month (reduces noise from the full category list). */
  const [relevantCategoriesOnly, setRelevantCategoriesOnly] = useState(true)

  const addCat = useMutation({
    mutationFn: ({ category, paise }: { category: string; paise: number }) =>
      putBudgetCategory(category, paise),
    onSuccess: () => {
      setNewCat('')
      setNewAmt('')
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const delCat = useMutation({
    mutationFn: deleteBudgetCategory,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const renameCat = useMutation({
    mutationFn: ({ oldName, newName }: { oldName: string; newName: string }) =>
      renameBudgetCategory(oldName, newName),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })

  const displayRows = useMemo(() => {
    if (q.data == null) {
      return []
    }
    const rows = q.data.rows
    if (!relevantCategoriesOnly) {
      return rows
    }
    return rows.filter((r) => r.budget_paise != null || r.spent_paise > 0)
  }, [q.data, relevantCategoriesOnly])

  if (q.isPending) {
    return <PageLoading lines={4} showFooterBlock />
  }

  if (q.isError) {
    return (
      <PageError title="Could not load budgets" message={<p className="text-sm">{String(q.error)}</p>} />
    )
  }

  const data = q.data

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Planning"
        title="Budget"
        description={
          <>
            FY <span className="font-semibold text-emerald-800">{data.fy}</span>
            <span className="text-zinc-400"> · </span>
            calendar month vs monthly caps
            <span className="text-zinc-400"> · </span>
            auto-refresh 30s
          </>
        }
        actions={
          <label className="flex flex-col gap-1.5 text-xs font-medium uppercase tracking-wide text-zinc-500">
            Calendar month
            <input
              type="month"
              value={ym}
              onChange={(e) => setYm(e.target.value)}
              className="h-10 rounded-lg border border-zinc-200 bg-white px-3 text-sm font-normal normal-case tracking-normal text-zinc-900 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/25"
            />
          </label>
        }
      />

      <section>
        <SectionTitle>Add or replace category budget</SectionTitle>
        <Panel variant="emerald">
        <h2 className="sr-only">Add or replace category budget</h2>
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-600">
          Creates a line for the current FY. Double-click a category name in the table to rename it
          (updates budgets, transactions, and rules).
        </p>
        <form
          className="mt-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end"
          onSubmit={(e) => {
            e.preventDefault()
            const name = newCat.trim()
            if (!name) {
              return
            }
            const n = Number.parseFloat(newAmt.replace(/,/g, ''))
            if (Number.isNaN(n) || n < 0) {
              return
            }
            addCat.mutate({ category: name, paise: Math.round(n * 100) })
          }}
        >
          <label className="text-xs font-medium text-zinc-700">
            Category name
            <input
              className="mt-1.5 block h-10 w-full min-w-[12rem] rounded-lg border border-zinc-200 bg-white px-3 text-sm text-zinc-900 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
              value={newCat}
              onChange={(e) => setNewCat(e.target.value)}
              placeholder="e.g. Food Delivery"
            />
          </label>
          <label className="text-xs font-medium text-zinc-700">
            Monthly cap (₹)
            <input
              className="mt-1.5 block h-10 w-36 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums text-zinc-900 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/20"
              inputMode="decimal"
              value={newAmt}
              onChange={(e) => setNewAmt(e.target.value)}
            />
          </label>
          <button
            type="submit"
            disabled={addCat.isPending}
            className="h-10 rounded-lg bg-emerald-700 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-50"
          >
            Save budget
          </button>
        </form>
        {addCat.isError ? <p className="mt-3 text-sm text-red-600">{String(addCat.error)}</p> : null}
        </Panel>
      </section>

      <section>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
          <SectionTitle className="!mb-0">Monthly breakdown</SectionTitle>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-700">
            <input
              type="checkbox"
              className="size-4 rounded border-zinc-300 text-emerald-700 focus:ring-emerald-500"
              checked={relevantCategoriesOnly}
              onChange={(e) => setRelevantCategoriesOnly(e.target.checked)}
            />
            Only categories with a cap or spend this month
          </label>
        </div>
        <p className="mt-2 max-w-3xl text-xs leading-relaxed text-zinc-600">
          <span className="font-medium text-zinc-700">Remove cap</span> deletes the monthly limit for
          this financial year only. Past transactions and category names elsewhere are unchanged.
        </p>
        <div className="mt-4 overflow-x-auto rounded-2xl border border-zinc-200/90 bg-white shadow-md shadow-zinc-900/5 ring-1 ring-zinc-900/[0.04]">
          <table className="w-full min-w-[52rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-zinc-200 bg-zinc-50/95 text-left text-[11px] font-semibold uppercase tracking-wider text-zinc-500 backdrop-blur-sm">
                <th className="sticky top-0 z-10 bg-zinc-50/95 py-3.5 pl-5 pr-3">Category</th>
                <th className="sticky top-0 z-10 bg-zinc-50/95 px-3 py-3.5 text-right">Budget / mo</th>
                <th className="sticky top-0 z-10 bg-zinc-50/95 px-3 py-3.5 text-right">Spent</th>
                <th className="sticky top-0 z-10 min-w-[12rem] bg-zinc-50/95 px-3 py-3.5">
                  Utilisation
                </th>
                <th className="sticky top-0 z-10 bg-zinc-50/95 px-3 py-3.5">Status</th>
                <th className="sticky top-0 z-10 min-w-[7.5rem] bg-zinc-50/95 py-3.5 pl-3 pr-5 text-right">
                  Action
                </th>
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row, i) => (
                <tr
                  key={row.category}
                  className={[
                    'border-b border-zinc-100 transition-colors last:border-b-0',
                    i % 2 === 0 ? 'bg-white' : 'bg-zinc-50/40',
                    'hover:bg-emerald-50/30',
                  ].join(' ')}
                >
                  <td className="max-w-[16rem] py-3.5 pl-5 pr-3 align-middle">
                    <EditableCategoryName
                      category={row.category}
                      disabled={mutation.isPending || delCat.isPending || renameCat.isPending}
                      onRename={async (next) => {
                        await renameCat.mutateAsync({ oldName: row.category, newName: next })
                      }}
                    />
                  </td>
                  <td className="px-3 py-3.5 align-middle">
                    <div className="flex justify-end">
                      <BudgetInput
                        key={`${row.category}-${row.budget_paise ?? 0}`}
                        category={row.category}
                        budgetPaise={row.budget_paise}
                        disabled={mutation.isPending}
                        onSave={(paise) => mutation.mutate({ category: row.category, paise })}
                      />
                    </div>
                  </td>
                  <td className="px-3 py-3.5 text-right align-middle tabular-nums text-[15px] font-medium text-zinc-800">
                    {formatPaise(row.spent_paise)}
                  </td>
                  <td className="min-w-[12rem] px-3 py-3.5 align-middle">
                    <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3">
                      <div className="h-2.5 min-w-[7rem] flex-1 overflow-hidden rounded-full bg-zinc-100 ring-1 ring-inset ring-zinc-200/70">
                        <div
                          className={[
                            'h-full rounded-full transition-all duration-300',
                            row.status === 'over'
                              ? 'bg-gradient-to-r from-red-600 to-red-500'
                              : row.status === 'warn'
                                ? 'bg-gradient-to-r from-amber-500 to-amber-400'
                                : row.status === 'full' || row.status === 'ok'
                                  ? 'bg-gradient-to-r from-emerald-600 to-emerald-500'
                                  : 'bg-zinc-300',
                          ].join(' ')}
                          style={{
                            width: `${row.pct_of_budget != null ? Math.min(row.pct_of_budget * 100, 100) : 0}%`,
                          }}
                        />
                      </div>
                      <span className="shrink-0 text-xs font-medium tabular-nums text-zinc-600 sm:min-w-[2.75rem] sm:text-right">
                        {row.pct_of_budget != null ? `${(row.pct_of_budget * 100).toFixed(0)}%` : '—'}
                      </span>
                    </div>
                  </td>
                  <td className="px-3 py-3.5 align-middle">
                    <span
                      className={`inline-flex max-w-full rounded-full px-2.5 py-1 text-xs font-semibold ${statusStyles(row.status)}`}
                    >
                      {statusLabel(row.status)}
                    </span>
                  </td>
                  <td className="py-3.5 pl-3 pr-5 text-right align-middle">
                    {row.budget_paise != null ? (
                      <button
                        type="button"
                        disabled={delCat.isPending}
                        className="inline-flex items-center justify-center rounded-md px-2.5 py-1.5 text-xs font-semibold text-red-700 transition hover:bg-red-50 disabled:opacity-50"
                        onClick={() => {
                          if (
                            window.confirm(
                              `Remove the monthly cap for “${row.category}” for this financial year?`,
                            )
                          ) {
                            delCat.mutate(row.category)
                          }
                        }}
                      >
                        Remove cap
                      </button>
                    ) : (
                      <span className="text-xs text-zinc-400" title="No cap set — add a budget above or leave as tracking-only spend">
                        No cap
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {displayRows.length === 0 ? (
            <p className="border-t border-zinc-100 bg-zinc-50/50 px-5 py-6 text-center text-sm text-zinc-600">
              No rows match this filter for {data.month}. Turn off &quot;Only categories with a cap or
              spend&quot; to see the full category list, or set a monthly cap above.
            </p>
          ) : null}
        </div>
      </section>
      {mutation.isError ? (
        <p className="text-sm text-red-600">{String(mutation.error)}</p>
      ) : null}
      {delCat.isError ? <p className="text-sm text-red-600">{String(delCat.error)}</p> : null}
      {renameCat.isError ? <p className="text-sm text-red-600">{String(renameCat.error)}</p> : null}
    </div>
  )
}
