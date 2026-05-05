import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

import { formatPaise } from '@/lib/format'

const COLORS = [
  '#0d9488',
  '#6366f1',
  '#d946ef',
  '#f97316',
  '#eab308',
  '#22c55e',
  '#3b82f6',
  '#ef4444',
  '#14b8a6',
  '#a855f7',
  '#f43f5e',
  '#84cc16',
]

type Slice = { name: string; value: number }

export function CategoryDonut({ byCategory }: { byCategory: Record<string, number> }) {
  const data: Slice[] = Object.entries(byCategory)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value)

  const totalPaise = data.reduce((s, d) => s + d.value, 0)

  if (data.length === 0) {
    return (
      <div className="flex min-h-[240px] items-center justify-center rounded-2xl border border-dashed border-zinc-300/80 bg-gradient-to-b from-zinc-50/80 to-white p-8 text-center text-sm text-zinc-500 shadow-inner">
        <div>
          <p className="font-medium text-zinc-600">No category spend this month yet</p>
          <p className="mt-1 text-xs text-zinc-400">Log expenses or import a file to see the breakdown.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full min-w-0 overflow-hidden rounded-2xl border border-emerald-200/50 bg-gradient-to-br from-emerald-50/30 via-white to-white p-6 shadow-lg shadow-emerald-900/5 ring-1 ring-emerald-900/[0.04]">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2 border-b border-zinc-100 pb-4">
        <div>
          <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-600">Spending mix</h3>
          <p className="mt-0.5 text-xs text-zinc-500">Share of this month&apos;s spend by category</p>
        </div>
        <div className="text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">Total</p>
          <p className="text-lg font-bold tabular-nums text-emerald-900">{formatPaise(totalPaise)}</p>
        </div>
      </div>

      <div className="flex flex-col items-stretch gap-8 lg:flex-row lg:items-center lg:gap-10">
        <div className="relative mx-auto w-full max-w-[min(100%,320px)] shrink-0">
          <ResponsiveContainer width="100%" height={260} minWidth={0}>
            <PieChart margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
              <Pie
                data={data}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius="58%"
                outerRadius="88%"
                paddingAngle={2}
                label={false}
                stroke="#fff"
                strokeWidth={2}
              >
                {data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) => {
                  const v = typeof value === 'number' ? value : Number(value ?? 0)
                  const pct = totalPaise > 0 ? ((v / totalPaise) * 100).toFixed(1) : '0'
                  return [`${formatPaise(v)} (${pct}%)`, 'Amount']
                }}
                contentStyle={{
                  borderRadius: 10,
                  border: '1px solid oklch(0.9 0.01 260)',
                  boxShadow: '0 10px 40px -10px rgb(0 0 0 / 0.15)',
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center pt-1">
            <div className="text-center">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-400">This month</p>
              <p className="mt-0.5 text-base font-bold tabular-nums text-zinc-800">{formatPaise(totalPaise)}</p>
            </div>
          </div>
        </div>

        <ul className="min-h-0 min-w-0 flex-1 space-y-2 overflow-y-auto pr-1 lg:max-h-[280px]">
          {data.map((d, i) => {
            const pct = totalPaise > 0 ? (d.value / totalPaise) * 100 : 0
            return (
              <li
                key={d.name}
                className="flex items-center gap-3 rounded-xl border border-zinc-100/80 bg-white/80 px-3 py-2.5 shadow-sm transition hover:border-emerald-200/60 hover:bg-emerald-50/30"
              >
                <span
                  className="h-3 w-3 shrink-0 rounded-sm shadow-sm ring-1 ring-black/5"
                  style={{ backgroundColor: COLORS[i % COLORS.length] }}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-zinc-800">{d.name}</p>
                  <p className="text-xs tabular-nums text-zinc-500">{formatPaise(d.value)}</p>
                </div>
                <span className="shrink-0 rounded-md bg-zinc-100 px-2 py-0.5 text-xs font-semibold tabular-nums text-zinc-700">
                  {pct.toFixed(0)}%
                </span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
