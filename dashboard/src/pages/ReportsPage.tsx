import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { downloadFYSummaryPdf, fetchFYSpending, fetchFYSummary, fetchSettings } from '@/lib/api'
import { formatPaiseCompact } from '@/lib/format'


export function ReportsPage() {
  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const [fyInput, setFyInput] = useState('')
  const [pdfLoading, setPdfLoading] = useState(false)

  const effectiveFy = useMemo(() => {
    const t = fyInput.trim()
    if (t) {
      return t
    }
    return settings.data?.current_fy?.trim() ?? ''
  }, [fyInput, settings.data?.current_fy])

  const spending = useQuery({
    queryKey: ['fy-spending', effectiveFy],
    queryFn: () => fetchFYSpending(effectiveFy),
    enabled: Boolean(effectiveFy) && Boolean(settings.data),
  })

  const summary = useQuery({
    queryKey: ['fy-summary', effectiveFy],
    queryFn: () => fetchFYSummary(effectiveFy),
    enabled: Boolean(effectiveFy) && Boolean(settings.data),
  })

  if (settings.isPending) {
    return <PageLoading lines={3} />
  }

  if (settings.isError) {
    return (
      <PageError title="Could not load settings" message={<p className="text-sm">{String(settings.error)}</p>} />
    )
  }

  if (effectiveFy && (spending.isError || summary.isError)) {
    return (
      <PageError
        title="Could not load report"
        message={<p className="text-sm">{String(spending.error ?? summary.error)}</p>}
      />
    )
  }

  const chartData =
    spending.data?.rows.map((r) => ({
      label: r.label,
      spent_rupees: r.spent_paise / 100,
    })) ?? []

  const sum = summary.data
  const reportLoading = Boolean(effectiveFy) && (spending.isPending || summary.isPending)

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Analytics"
        title="Reports"
        description="Spending by FY month (April–March)"
        actions={
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex flex-col text-xs font-medium text-zinc-600">
              Financial year (YYYY-YY)
              <input
                className="mt-1 w-36 rounded-md border border-zinc-200 px-2 py-1.5 font-mono text-sm text-zinc-900"
                value={fyInput}
                onChange={(e) => setFyInput(e.target.value)}
                placeholder={settings.data?.current_fy}
                aria-label="Financial year YYYY-YY"
              />
            </label>
            <button
              type="button"
              className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-800 shadow-sm hover:bg-zinc-50 disabled:opacity-50"
              disabled={!effectiveFy || pdfLoading}
              onClick={() => {
                setPdfLoading(true)
                void downloadFYSummaryPdf(effectiveFy || undefined)
                  .catch((e: unknown) => {
                    console.error(e)
                    window.alert(e instanceof Error ? e.message : String(e))
                  })
                  .finally(() => setPdfLoading(false))
              }}
            >
              {pdfLoading ? 'Preparing PDF…' : 'Download PDF'}
            </button>
          </div>
        }
      />

      {reportLoading ? (
        <div className="animate-pulse space-y-4">
          <div className="h-24 rounded-2xl bg-zinc-100/90" />
          <div className="h-72 rounded-2xl bg-zinc-100/90" />
        </div>
      ) : null}

      {!reportLoading && sum ? (
        <section className="grid gap-4 sm:grid-cols-3">
          <KpiCard tone="spending" label="FY spend" value={formatPaiseCompact(sum.total_spent_paise)} />
          <KpiCard
            tone="neutral"
            label="Income run-rate × 12"
            value={formatPaiseCompact(sum.total_monthly_income_run_rate_paise)}
          />
          <KpiCard
            tone="balance"
            label="Implied balance"
            value={formatPaiseCompact(sum.implied_savings_paise)}
          />
        </section>
      ) : null}

      {!reportLoading && spending.data ? (
        <section>
          <SectionTitle>Monthly spending · {spending.data.fy}</SectionTitle>
          <Panel>
          <h2 className="sr-only">Monthly spending · {spending.data.fy}</h2>
          <div className="w-full min-w-0">
            <ResponsiveContainer width="100%" height={320} minWidth={0}>
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-zinc-200" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} className="text-zinc-600" />
                <YAxis
                  tickFormatter={(v) => formatPaiseCompact(Math.round(v * 100))}
                  width={72}
                  tick={{ fontSize: 10 }}
                />
                <Tooltip
                  formatter={(value) => {
                    const v = typeof value === 'number' ? value : Number(value)
                    return [formatPaiseCompact(Math.round(v * 100)), 'Spent']
                  }}
                />
                <Bar dataKey="spent_rupees" fill="#047857" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          </Panel>
        </section>
      ) : null}

      {!reportLoading && spending.data ? (
        <section>
          <SectionTitle>Month by month</SectionTitle>
          <Panel variant="table" padding={false}>
          <table className="w-full text-left text-sm">
            <thead className="bg-zinc-50 text-xs font-medium uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-2">Month</th>
                <th className="px-4 py-2 text-right">Spent</th>
              </tr>
            </thead>
            <tbody>
              {spending.data.rows.map((r) => (
                <tr key={r.fy_month} className="border-t border-zinc-100">
                  <td className="px-4 py-2 text-zinc-800">
                    {r.label}{' '}
                    <span className="text-xs text-zinc-400">
                      ({r.start_date} – {r.end_date})
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-zinc-900">
                    {formatPaiseCompact(r.spent_paise)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </Panel>
        </section>
      ) : null}
    </div>
  )
}
