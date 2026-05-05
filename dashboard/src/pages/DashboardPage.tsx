import { useQuery } from '@tanstack/react-query'

import { IndeterminateProgressBar } from '@/components/ui/IndeterminateProgressBar'
import { AlertsBanner } from '@/components/dashboard/AlertsBanner'
import { CategoryDonut } from '@/components/dashboard/CategoryDonut'
import { KpiCard } from '@/components/dashboard/KpiCard'
import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { fetchDashboardAlerts, fetchDashboardSummary } from '@/lib/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'


export function DashboardPage() {
  const summary = useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: fetchDashboardSummary,
  })

  const alerts = useQuery({
    queryKey: ['dashboard-alerts'],
    queryFn: fetchDashboardAlerts,
  })

  if (summary.isPending) {
    return (
      <div className="space-y-6">
        <IndeterminateProgressBar label="Loading overview…" />
        <PageLoading lines={5} showFooterBlock />
      </div>
    )
  }

  if (summary.isError) {
    return (
      <PageError
        title="Could not reach the API"
        message={
          <>
            <p>
              Start the FastAPI server (
              <code className="rounded-md bg-red-100/80 px-1.5 py-0.5">uv run uvicorn finance_api.main:app</code>) or run{' '}
              <code className="rounded-md bg-red-100/80 px-1.5 py-0.5">uv run python start.py</code> from the repo root.
            </p>
            <p className="mt-2 text-red-800">{String(summary.error)}</p>
          </>
        }
      />
    )
  }

  const s = summary.data

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Dashboard"
        title="Overview"
        description={
          <>
            Financial year <span className="font-semibold text-emerald-900">{s.current_fy}</span>
            <span className="text-zinc-400"> · </span>
            figures refresh automatically every 30 seconds
          </>
        }
      />

      {alerts.data ? <AlertsBanner data={alerts.data} /> : null}

      <section>
        <SectionTitle>Spending</SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          <KpiCard tone="spending" label="Today" value={formatPaise(s.spent_today_paise)} />
          <KpiCard tone="spending" label="This week" value={formatPaise(s.spent_week_paise)} />
          <KpiCard tone="spending" label="This month" value={formatPaise(s.spent_month_paise)} />
          <KpiCard
            tone="spending"
            label="Monthly income (est.)"
            value={s.monthly_income_paise != null ? formatPaiseCompact(s.monthly_income_paise) : '—'}
            hint={
              s.monthly_income_paise == null
                ? 'Add income streams under Income & tax'
                : undefined
            }
          />
          <KpiCard
            tone="spending"
            label="Savings rate"
            value={
              s.savings_rate_month != null ? `${(s.savings_rate_month * 100).toFixed(1)}%` : '—'
            }
            hint={
              s.savings_rate_month == null
                ? 'Needs monthly income (Income & tax) and spending this month'
                : undefined
            }
          />
        </div>
      </section>

      <section>
        <SectionTitle>Position</SectionTitle>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard tone="balance" label="Total debt" value={formatPaiseCompact(s.total_debt_paise)} />
          <KpiCard
            tone="balance"
            label="Net worth"
            value={s.net_worth_paise != null ? formatPaiseCompact(s.net_worth_paise) : '—'}
          />
          <KpiCard tone="balance" label="Portfolio" value={formatPaiseCompact(s.portfolio_value_paise)} />
          <KpiCard tone="neutral" label="FY" value={s.current_fy} />
        </div>
      </section>

      <section>
        <SectionTitle>This month by category</SectionTitle>
        <CategoryDonut byCategory={s.spent_by_category_month} />
      </section>

      {Object.keys(s.spent_by_account_month).length > 0 && (
        <section>
          <SectionTitle>This month by account</SectionTitle>
          <Panel>
            <div className="divide-y divide-zinc-100">
              {Object.entries(s.spent_by_account_month)
                .sort(([, a], [, b]) => b - a)
                .map(([acct, paise]) => {
                  const total = Object.values(s.spent_by_account_month).reduce((s, v) => s + v, 0)
                  const pct = total > 0 ? (paise / total) * 100 : 0
                  return (
                    <div key={acct} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between text-sm">
                          <span className="font-medium text-zinc-800">{acct}</span>
                          <span className="tabular-nums text-zinc-700">{formatPaise(paise)}</span>
                        </div>
                        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-zinc-100">
                          <div
                            className="h-full rounded-full bg-blue-500"
                            style={{ width: `${pct.toFixed(1)}%` }}
                          />
                        </div>
                      </div>
                      <span className="w-10 text-right text-xs tabular-nums text-zinc-500">
                        {pct.toFixed(0)}%
                      </span>
                    </div>
                  )
                })}
            </div>
          </Panel>
        </section>
      )}
    </div>
  )
}
