import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { INVESTMENT_TYPES } from '@/constants/investments'
import { fetchInvestments, putInvestment } from '@/lib/api'
import { formatPaiseCompact } from '@/lib/format'
import type { InvestmentOut } from '@/types/api'

const SECTOR_COLORS = ['#047857', '#0d9488', '#0891b2', '#2563eb', '#7c3aed', '#db2777', '#ea580c', '#ca8a04']

const TAX_OPTIONS = [
  { value: 'unspecified', label: 'Unspecified' },
  { value: 'ltcg', label: 'LTCG (≥1y equity)' },
  { value: 'stcg', label: 'STCG (<1y equity)' },
] as const

function isStockOrEtf(row: InvestmentOut): boolean {
  return row.type === 'Stock' || row.type === 'ETF'
}

export function StocksPortfolioPage() {
  const qc = useQueryClient()
  const [sectorDraft, setSectorDraft] = useState<Record<number, string>>({})

  const inv = useQuery({
    queryKey: ['investments'],
    queryFn: fetchInvestments,
  })

  const up = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: {
        sector?: string | null
        equity_tax_class?: string
        type?: string
        instrument?: string
      }
    }) => putInvestment(id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['investments'] })
      void qc.invalidateQueries({ queryKey: ['portfolio-summary'] })
    },
  })

  const stocks = useMemo(() => (inv.data ?? []).filter(isStockOrEtf), [inv.data])

  const sectorWeights = useMemo(() => {
    const m = new Map<string, number>()
    for (const row of stocks) {
      const label = row.sector?.trim() || 'Unassigned'
      const mv = row.market_value_paise ?? 0
      m.set(label, (m.get(label) ?? 0) + mv)
    }
    const total = [...m.values()].reduce((a, b) => a + b, 0)
    return [...m.entries()]
      .map(([name, paise]) => ({
        name,
        paise,
        pct: total > 0 ? Math.round((paise / total) * 1000) / 10 : 0,
      }))
      .sort((a, b) => b.paise - a.paise)
  }, [stocks])

  const pieData = sectorWeights.map((s) => ({
    name: s.name,
    value: Math.round(s.paise / 100),
  }))

  if (inv.isPending) {
    return <PageLoading lines={3} showFooterBlock />
  }

  if (inv.isError) {
    return (
      <PageError title="Could not load holdings" message={<p className="text-sm">{String(inv.error)}</p>} />
    )
  }

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Equities"
        title="Stocks & ETFs"
        description={
          <>
            <span className="mb-1 block text-xs font-medium text-emerald-700">
              <Link to="/investments" className="hover:underline">
                ← All investments
              </Link>
            </span>
            Sector weights (by market value), and LTCG vs STCG tags for planning — not tax advice.
          </>
        }
      />

      {sectorWeights.length > 0 ? (
        <section>
          <SectionTitle>Sector weights</SectionTitle>
          <Panel>
          <h2 className="sr-only">Sector weights</h2>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="h-64 min-h-[16rem] w-full min-w-0">
              <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={0}>
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={90}
                    label={({ name, percent }) =>
                      `${name} (${((percent ?? 0) * 100).toFixed(0)}%)`
                    }
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => [`₹${Number(v).toLocaleString('en-IN')}`, 'MV']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="space-y-2 text-sm">
              {sectorWeights.map((s) => (
                <li
                  key={s.name}
                  className="flex justify-between gap-4 border-b border-zinc-100 py-1.5 tabular-nums"
                >
                  <span className="text-zinc-800">{s.name}</span>
                  <span className="text-zinc-600">
                    {formatPaiseCompact(s.paise)} ({s.pct}%)
                  </span>
                </li>
              ))}
            </ul>
          </div>
          </Panel>
        </section>
      ) : (
        <p className="text-sm text-zinc-600">
          No stock or ETF rows yet. Add holdings with type &quot;Stock&quot; or &quot;ETF&quot; on the main{' '}
          <Link to="/investments" className="font-medium text-emerald-800 underline">
            Investments
          </Link>{' '}
          page.
        </p>
      )}

      <section>
        <SectionTitle>Holdings</SectionTitle>
        <Panel variant="table" padding={false}>
        <h2 className="sr-only">Holdings</h2>
        <div className="overflow-x-auto border-b border-zinc-100">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="bg-zinc-50 text-xs font-medium uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2">Instrument</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Sector</th>
                <th className="px-3 py-2">CGT tag</th>
                <th className="px-3 py-2 text-right">Market value</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((row) => (
                <tr key={row.id} className="border-t border-zinc-100">
                  <td className="px-3 py-2 font-medium text-zinc-900">{row.instrument}</td>
                  <td className="px-3 py-2 text-zinc-700">
                    <select
                      className="max-w-[10rem] rounded border border-zinc-200 bg-white px-1.5 py-1 text-xs"
                      value={row.type}
                      onChange={(e) => {
                        up.mutate({ id: row.id, body: { type: e.target.value } })
                      }}
                    >
                      {INVESTMENT_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <input
                      className="w-36 max-w-full rounded border border-zinc-200 px-2 py-1 text-xs"
                      placeholder="e.g. Banking"
                      value={sectorDraft[row.id] ?? row.sector ?? ''}
                      onChange={(e) => setSectorDraft((d) => ({ ...d, [row.id]: e.target.value }))}
                      onBlur={() => {
                        const v = (sectorDraft[row.id] ?? row.sector ?? '').trim()
                        if (v === (row.sector ?? '').trim()) {
                          return
                        }
                        up.mutate({
                          id: row.id,
                          body: { sector: v || null },
                        })
                      }}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <select
                      className="rounded border border-zinc-200 bg-white px-1.5 py-1 text-xs"
                      value={row.equity_tax_class ?? 'unspecified'}
                      onChange={(e) => {
                        up.mutate({
                          id: row.id,
                          body: { equity_tax_class: e.target.value },
                        })
                      }}
                    >
                      {TAX_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-800">
                    {row.market_value_paise != null ? formatPaiseCompact(row.market_value_paise) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </Panel>
      </section>
    </div>
  )
}
