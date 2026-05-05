import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
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
import { fetchNetWorthHistory, postNetWorthSnapshotComputed } from '@/lib/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'


function paiseToRupeeLabel(paise: number): string {
  const r = paise / 100
  if (Math.abs(r) >= 1e7) {
    return `₹${(r / 1e7).toFixed(2)} Cr`
  }
  if (Math.abs(r) >= 1e5) {
    return `₹${(r / 1e5).toFixed(2)} L`
  }
  return `₹${r.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

export function NetWorthPage() {
  const qc = useQueryClient()

  const history = useQuery({
    queryKey: ['net-worth-history'],
    queryFn: () => fetchNetWorthHistory(365),
  })

  const recordSnapshot = useMutation({
    mutationFn: postNetWorthSnapshotComputed,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['net-worth-history'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  if (history.isPending) {
    return <PageLoading lines={3} showFooterBlock />
  }

  if (history.isError) {
    return (
      <PageError
        title="Could not load net worth history"
        message={<p className="text-sm">{String(history.error)}</p>}
      />
    )
  }

  const rows = history.data
  const latest = rows.length ? rows[rows.length - 1] : null

  const chartData = rows.map((r) => ({
    date: r.snapshot_date,
    net: r.net_worth_paise / 100,
    assets: r.total_assets_paise / 100,
    liabilities: r.total_liabilities_paise / 100,
  }))

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Wealth"
        title="Net worth"
        description="Snapshot history · portfolio + fixed income − active debt (computed) · refreshes every 30s"
        actions={
          <button
            type="button"
            disabled={recordSnapshot.isPending}
            onClick={() => recordSnapshot.mutate()}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-emerald-800 disabled:opacity-50"
          >
            {recordSnapshot.isPending ? 'Recording…' : 'Record snapshot (from holdings)'}
          </button>
        }
      />

      {recordSnapshot.isError ? (
        <p className="text-sm text-red-700">{String(recordSnapshot.error)}</p>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-3">
        <KpiCard
          tone="neutral"
          label="Assets (latest)"
          value={latest ? formatPaiseCompact(latest.total_assets_paise) : '—'}
        />
        <KpiCard
          tone="neutral"
          label="Liabilities (latest)"
          value={latest ? formatPaiseCompact(latest.total_liabilities_paise) : '—'}
        />
        <KpiCard
          tone="balance"
          label="Net worth"
          value={latest ? formatPaiseCompact(latest.net_worth_paise) : '—'}
        />
      </section>

      {rows.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-zinc-300 bg-zinc-50/80 p-8 text-center text-zinc-600 shadow-sm ring-1 ring-zinc-900/[0.04]">
          <p>No snapshots yet. Use the button above to record today&apos;s totals from your holdings.</p>
        </div>
      ) : (
        <section>
          <SectionTitle>Trend</SectionTitle>
          <Panel>
          <h2 className="sr-only">Trend</h2>
          <div className="w-full min-w-0">
            <ResponsiveContainer width="100%" height={320} minWidth={0}>
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-zinc-200" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} className="text-zinc-600" />
                <YAxis
                  tickFormatter={(v) => paiseToRupeeLabel(v * 100)}
                  width={72}
                  tick={{ fontSize: 11 }}
                  className="text-zinc-600"
                />
                <Tooltip
                  formatter={(value, _name, item) => {
                    const v = typeof value === 'number' ? value : Number(value)
                    // Recharts passes display `name` on each Line, not dataKey — use dataKey for labels.
                    const key = item?.dataKey
                    const label =
                      key === 'net'
                        ? 'Net worth'
                        : key === 'assets'
                          ? 'Assets'
                          : 'Liabilities'
                    return [formatPaise(Math.round(v * 100)), label]
                  }}
                  labelFormatter={(label) => String(label)}
                />
                <Legend />
                <Line type="monotone" dataKey="net" name="Net worth" stroke="#047857" strokeWidth={2} dot={false} />
                <Line
                  type="monotone"
                  dataKey="assets"
                  name="Assets"
                  stroke="#0ea5e9"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="liabilities"
                  name="Liabilities"
                  stroke="#f97316"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          </Panel>
        </section>
      )}

      {rows.length > 0 ? (
        <section>
          <SectionTitle>Snapshots</SectionTitle>
          <Panel variant="table" padding={false}>
          <h2 className="sr-only">Snapshots</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-zinc-50 text-xs font-medium uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2 text-right">Assets</th>
                  <th className="px-4 py-2 text-right">Liabilities</th>
                  <th className="px-4 py-2 text-right">Net</th>
                </tr>
              </thead>
              <tbody>
                {[...rows].reverse().map((r) => (
                  <tr key={r.id} className="border-t border-zinc-100">
                    <td className="px-4 py-2 font-medium text-zinc-900">{r.snapshot_date}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-zinc-800">
                      {formatPaiseCompact(r.total_assets_paise)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-zinc-800">
                      {formatPaiseCompact(r.total_liabilities_paise)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-zinc-900">
                      {formatPaiseCompact(r.net_worth_paise)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </Panel>
        </section>
      ) : null}
    </div>
  )
}
