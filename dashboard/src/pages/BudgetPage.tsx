import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Plus } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { Panel } from '@/components/ui/Panel'
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
      return 'bg-emerald-100 text-emerald-800'
    case 'full':
      return 'bg-sky-100 text-sky-900'
    case 'warn':
      return 'bg-amber-100 text-amber-900'
    case 'over':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-zinc-100 text-zinc-500'
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
      return 'Over'
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
      /* keep editing */
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
        className="w-full min-w-0 max-w-[12rem] rounded border border-emerald-500 px-2 py-0.5 text-xs font-medium focus:outline-none disabled:opacity-50"
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
          : 'cursor-pointer font-medium text-zinc-900 hover:text-emerald-800'
      }
      title={disabled ? undefined : 'Double-click to rename'}
      onDoubleClick={() => {
        if (!disabled) {
          setVal(category)
          setEditing(true)
        }
      }}
      onKeyDown={(e) => {
        if (disabled) return
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
      className="h-8 w-full min-w-[5.5rem] max-w-[7.5rem] rounded border border-zinc-200 bg-zinc-50/50 px-2 text-right text-xs font-medium tabular-nums focus:border-emerald-500 focus:bg-white focus:outline-none disabled:opacity-50"
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
  const [addOpen, setAddOpen] = useState(false)
  const [relevantCategoriesOnly, setRelevantCategoriesOnly] = useState(true)

  const addCat = useMutation({
    mutationFn: ({ category, paise }: { category: string; paise: number }) =>
      putBudgetCategory(category, paise),
    onSuccess: () => {
      setNewCat('')
      setNewAmt('')
      setAddOpen(false)
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
    if (q.data == null) return []
    const rows = q.data.rows
    if (!relevantCategoriesOnly) return rows
    return rows.filter((r) => r.budget_paise != null || r.spent_paise > 0)
  }, [q.data, relevantCategoriesOnly])

  const totals = useMemo(() => {
    let budget = 0
    let spent = 0
    for (const r of displayRows) {
      spent += r.spent_paise
      if (r.budget_paise != null) budget += r.budget_paise
    }
    return { budget, spent }
  }, [displayRows])

  if (q.isPending) return <PageLoading lines={4} showFooterBlock />

  if (q.isError) {
    return (
      <PageError title="Could not load budgets" message={<p className="text-sm">{String(q.error)}</p>} />
    )
  }

  const data = q.data

  return (
    <div className="flex h-[calc(100dvh-3rem)] flex-col gap-2 lg:h-[calc(100dvh-4rem)]">
      <div className="shrink-0 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-900">Budget</h1>
            <p className="text-xs text-zinc-500">
              FY {data.fy} · {displayRows.length} categor{displayRows.length !== 1 ? 'ies' : 'y'}
              {totals.budget > 0 ? (
                <>
                  {' '}
                  · cap {formatPaise(totals.budget)} · spent {formatPaise(totals.spent)}
                </>
              ) : totals.spent > 0 ? (
                <> · spent {formatPaise(totals.spent)}</>
              ) : null}
            </p>
          </div>
          <input
            type="month"
            value={ym}
            onChange={(e) => setYm(e.target.value)}
            className="rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-xs text-zinc-900"
            aria-label="Calendar month"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200/80 bg-white px-3 py-2 shadow-sm ring-1 ring-zinc-900/[0.03]">
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-700">
            <input
              type="checkbox"
              className="size-3.5 rounded border-zinc-300 text-emerald-700"
              checked={relevantCategoriesOnly}
              onChange={(e) => setRelevantCategoriesOnly(e.target.checked)}
            />
            Cap or spend only
          </label>

          <span className="hidden h-4 w-px bg-zinc-200 sm:block" aria-hidden />

          <button
            type="button"
            onClick={() => setAddOpen((o) => !o)}
            className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700"
          >
            {addOpen ? (
              <>
                <ChevronDown className="size-3.5 rotate-180" aria-hidden />
                Close
              </>
            ) : (
              <>
                <Plus className="size-3.5" aria-hidden />
                Add category
              </>
            )}
          </button>
        </div>

        {addOpen ? (
          <Panel padding={false}>
            <form
              className="flex flex-wrap items-end gap-2 p-3"
              onSubmit={(e) => {
                e.preventDefault()
                const name = newCat.trim()
                if (!name) return
                const n = Number.parseFloat(newAmt.replace(/,/g, ''))
                if (Number.isNaN(n) || n < 0) return
                addCat.mutate({ category: name, paise: Math.round(n * 100) })
              }}
            >
              <label className="flex flex-col gap-0.5 text-xs text-zinc-600">
                Category
                <input
                  className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                  value={newCat}
                  onChange={(e) => setNewCat(e.target.value)}
                  placeholder="Food Delivery"
                />
              </label>
              <label className="flex flex-col gap-0.5 text-xs text-zinc-600">
                Monthly cap (₹)
                <input
                  className="w-28 rounded-md border border-zinc-200 px-2 py-1.5 text-right text-xs tabular-nums"
                  inputMode="decimal"
                  value={newAmt}
                  onChange={(e) => setNewAmt(e.target.value)}
                />
              </label>
              <button
                type="submit"
                disabled={addCat.isPending}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              >
                Save
              </button>
              {addCat.isError ? (
                <p className="w-full text-xs text-red-600">{String(addCat.error)}</p>
              ) : null}
            </form>
          </Panel>
        ) : null}

        {(mutation.isError || delCat.isError || renameCat.isError) && (
          <p className="text-xs text-red-600">
            {String(mutation.error ?? delCat.error ?? renameCat.error)}
          </p>
        )}
      </div>

      <Panel variant="table" padding={false} className="min-h-0 flex-1 overflow-hidden">
        <div className="h-full overflow-auto">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2.5">Category</th>
                <th className="px-3 py-2.5 text-right">Budget</th>
                <th className="px-3 py-2.5 text-right">Spent</th>
                <th className="min-w-[9rem] px-3 py-2.5">Utilisation</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5 text-right"> </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {displayRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-zinc-500">
                    No rows for {data.month}. Add a category or turn off the filter.
                  </td>
                </tr>
              ) : (
                displayRows.map((row) => (
                  <tr key={row.category} className="hover:bg-zinc-50/80">
                    <td className="max-w-[14rem] px-3 py-2 align-middle">
                      <EditableCategoryName
                        category={row.category}
                        disabled={mutation.isPending || delCat.isPending || renameCat.isPending}
                        onRename={async (next) => {
                          await renameCat.mutateAsync({ oldName: row.category, newName: next })
                        }}
                      />
                    </td>
                    <td className="px-3 py-2 align-middle">
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
                    <td className="px-3 py-2 text-right align-middle tabular-nums text-zinc-800">
                      {formatPaise(row.spent_paise)}
                    </td>
                    <td className="px-3 py-2 align-middle">
                      <div className="flex items-center gap-2">
                        <div className="h-2 min-w-[5rem] flex-1 overflow-hidden rounded-full bg-zinc-100">
                          <div
                            className={[
                              'h-full rounded-full',
                              row.status === 'over'
                                ? 'bg-red-500'
                                : row.status === 'warn'
                                  ? 'bg-amber-500'
                                  : row.status === 'full' || row.status === 'ok'
                                    ? 'bg-emerald-500'
                                    : 'bg-zinc-300',
                            ].join(' ')}
                            style={{
                              width: `${row.pct_of_budget != null ? Math.min(row.pct_of_budget * 100, 100) : 0}%`,
                            }}
                          />
                        </div>
                        <span className="shrink-0 text-[10px] tabular-nums text-zinc-500">
                          {row.pct_of_budget != null ? `${(row.pct_of_budget * 100).toFixed(0)}%` : '—'}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-2 align-middle">
                      <span
                        className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium ${statusStyles(row.status)}`}
                      >
                        {statusLabel(row.status)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right align-middle">
                      {row.budget_paise != null ? (
                        <button
                          type="button"
                          disabled={delCat.isPending}
                          className="text-xs font-medium text-red-600 hover:underline disabled:opacity-50"
                          onClick={() => {
                            if (
                              window.confirm(
                                `Remove the monthly cap for "${row.category}" for this financial year?`,
                              )
                            ) {
                              delCat.mutate(row.category)
                            }
                          }}
                        >
                          Remove
                        </button>
                      ) : (
                        <span className="text-[10px] text-zinc-400">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}
