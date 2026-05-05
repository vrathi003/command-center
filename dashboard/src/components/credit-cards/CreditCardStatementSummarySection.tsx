import { useMemo, useState } from 'react'

import { Panel } from '@/components/ui/Panel'
import {
  aggregateStatementLineItems,
  type StatementGranularity,
} from '@/lib/creditCardStatementSummary'
import { formatPaiseCompact } from '@/lib/format'
import type { CreditCardStatementOut } from '@/types/api'

export function CreditCardStatementSummarySection({
  statements,
}: {
  statements: CreditCardStatementOut[]
}) {
  const [granularity, setGranularity] = useState<StatementGranularity>('month')

  const buckets = useMemo(
    () => aggregateStatementLineItems(statements, granularity),
    [statements, granularity],
  )

  const topCategories = useMemo(() => {
    const acc: Record<string, number> = {}
    for (const b of buckets) {
      for (const [k, v] of Object.entries(b.by_category_paise)) {
        acc[k] = (acc[k] ?? 0) + v
      }
    }
    return Object.entries(acc)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
  }, [buckets])

  if (statements.length === 0) {
    return null
  }

  return (
    <Panel variant="emerald">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-800">Statement spend summary</p>
          <p className="mt-1 text-xs text-zinc-500">
            Built from parsed line items across all uploads. Grouping uses each line&apos;s date (falls back to
            statement period if missing). Switch between monthly, quarterly, and annual views.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {(['month', 'quarter', 'year'] as const).map((g) => (
            <button
              key={g}
              type="button"
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold shadow-sm ${
                granularity === g
                  ? 'bg-emerald-700 text-white'
                  : 'border border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50'
              }`}
              onClick={() => setGranularity(g)}
            >
              {g === 'month' ? 'Monthly' : g === 'quarter' ? 'Quarterly' : 'Annual'}
            </button>
          ))}
        </div>
      </div>

      {buckets.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No dated spending lines yet. Upload statements where dates parse correctly (CSV with ISO dates
          works best).
        </p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-emerald-100/80">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="bg-emerald-50/80 text-xs font-semibold uppercase tracking-wide text-emerald-900/80">
                <tr>
                  <th className="px-3 py-2">Period</th>
                  <th className="px-3 py-2 text-right">Total spend</th>
                  <th className="px-3 py-2 text-right">Lines</th>
                  <th className="px-3 py-2 text-right">Statements</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 bg-white/60">
                {buckets.map((b) => (
                  <tr key={b.key}>
                    <td className="px-3 py-2 font-medium text-zinc-900">{b.label}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-zinc-800">
                      {formatPaiseCompact(b.total_paise)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-zinc-600">{b.line_count}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-zinc-600">{b.statement_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {topCategories.length > 0 ? (
            <div className="mt-6">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Top categories (same period grouping as the table)
              </p>
              <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {topCategories.map(([name, paise]) => (
                  <li
                    key={name}
                    className="flex items-center justify-between gap-2 rounded-lg border border-zinc-100 bg-zinc-50/50 px-3 py-2 text-sm"
                  >
                    <span className="truncate text-zinc-800">{name}</span>
                    <span className="shrink-0 tabular-nums font-medium text-zinc-900">
                      {formatPaiseCompact(paise)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      )}
    </Panel>
  )
}
