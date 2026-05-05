import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  deleteConstructionAllData,
  fetchConstructionTowerDashboard,
  fetchConstructionSnapshots,
  fetchConstructionZoneLabels,
  fetchConstructionZones,
  putConstructionZoneLabels,
  uploadConstructionPdf,
} from '@/lib/api'

/** Building height used when the PDF reports floor counts but no % column. */
const BUILDING_TOTAL_FLOORS = 26

function sortZoneKeys(keys: string[]): string[] {
  return [...keys].sort((a, b) => {
    const ta = /^tower:(\d+)$/.exec(a)
    const tb = /^tower:(\d+)$/.exec(b)
    if (ta && tb) return Number(ta[1]) - Number(tb[1])
    if (ta) return -1
    if (tb) return 1
    return a.localeCompare(b)
  })
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return `${n.toFixed(1)}%`
}

export function ConstructionPage() {
  const qc = useQueryClient()
  const [zoneKey, setZoneKey] = useState<string>('')
  const [labelDraft, setLabelDraft] = useState<Record<string, string>>({})
  const [showLabels, setShowLabels] = useState(false)

  const snapshots = useQuery({
    queryKey: ['construction-snapshots'],
    queryFn: () => fetchConstructionSnapshots(),
  })

  const zones = useQuery({
    queryKey: ['construction-zones'],
    queryFn: () => fetchConstructionZones(),
    enabled: snapshots.isSuccess,
  })

  const sortedZones = useMemo(() => sortZoneKeys(zones.data ?? []), [zones.data])
  const towerZones = useMemo(
    () => sortedZones.filter((z) => z.startsWith('tower:')),
    [sortedZones],
  )

  useEffect(() => {
    if (towerZones.length === 0) return
    if (!zoneKey || !towerZones.includes(zoneKey)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- pick first tower when list changes
      setZoneKey(towerZones[0])
    }
  }, [towerZones, zoneKey])

  const towerDashboard = useQuery({
    queryKey: ['construction-tower-dashboard', zoneKey, BUILDING_TOTAL_FLOORS],
    queryFn: () =>
      fetchConstructionTowerDashboard(zoneKey, { totalFloors: BUILDING_TOTAL_FLOORS }),
    enabled: Boolean(zoneKey && towerZones.includes(zoneKey)),
  })

  const zoneLabels = useQuery({
    queryKey: ['construction-zone-labels'],
    queryFn: () => fetchConstructionZoneLabels(),
    enabled: Boolean(zones.data && zones.data.length > 0),
  })

  useEffect(() => {
    if (zoneLabels.data?.labels) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror server labels into draft
      setLabelDraft(zoneLabels.data.labels)
    }
  }, [zoneLabels.data])

  const deleteAll = useMutation({
    mutationFn: () => deleteConstructionAllData(),
    onSuccess: () => {
      setZoneKey('')
      setLabelDraft({})
      void qc.invalidateQueries({ queryKey: ['construction-snapshots'] })
      void qc.invalidateQueries({ queryKey: ['construction-zones'] })
      void qc.invalidateQueries({ queryKey: ['construction-tower-dashboard'] })
      void qc.invalidateQueries({ queryKey: ['construction-zone-labels'] })
    },
  })

  const upload = useMutation({
    mutationKey: ['construction-upload'],
    mutationFn: (file: File) => uploadConstructionPdf(file),
    onSuccess: () => {
      deleteAll.reset()
      void qc.invalidateQueries({ queryKey: ['construction-snapshots'] })
      void qc.invalidateQueries({ queryKey: ['construction-zones'] })
      void qc.invalidateQueries({ queryKey: ['construction-tower-dashboard'] })
      void qc.invalidateQueries({ queryKey: ['construction-zone-labels'] })
    },
  })

  const saveLabels = useMutation({
    mutationFn: () =>
      putConstructionZoneLabels(
        Object.entries(labelDraft).map(([zone_key, label]) => ({ zone_key, label })),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['construction-zone-labels'] })
    },
  })

  const barData = useMemo(() => {
    const rows = towerDashboard.data?.activity_rows ?? []
    const sorted = [...rows].sort((a, b) => {
      const s = a.section.localeCompare(b.section)
      if (s !== 0) return s
      return a.activity_raw.localeCompare(b.activity_raw)
    })
    return sorted.map((r, i) => {
      const shortSec = r.section.length > 28 ? `${r.section.slice(0, 28)}…` : r.section
      const shortAct = r.activity_raw.length > 36 ? `${r.activity_raw.slice(0, 36)}…` : r.activity_raw
      return {
        key: `${r.section}-${r.activity_raw}-${i}`,
        label: `${shortSec} · ${shortAct}`,
        effective_pct: r.effective_pct ?? 0,
        floors_pct: r.floors_pct_of_total ?? null,
      }
    })
  }, [towerDashboard.data?.activity_rows])

  const trendChartData = useMemo(() => {
    const pts = towerDashboard.data?.trend ?? []
    return pts.map((p) => ({
      month: p.as_of_date.slice(0, 7),
      as_of: p.as_of_date,
      avgEffective: p.avg_effective_pct,
      avgFloors: p.avg_floors_pct,
      count: p.activity_count,
    }))
  }, [towerDashboard.data?.trend])

  const displayZone = (zk: string) => labelDraft[zk] ?? zoneLabels.data?.labels[zk] ?? zk

  if (snapshots.isPending) {
    return <PageLoading lines={4} />
  }

  if (snapshots.isError) {
    return (
      <PageError
        title="Construction progress"
        message={<p className="text-sm">{String(snapshots.error)}</p>}
      />
    )
  }

  return (
    <div className="space-y-8">
      <PageHero
        eyebrow="Property"
        title="Construction progress"
        description={`Upload monthly builder PDFs (same format each month). Towers follow table page order (tower 13 skipped). Completion uses PDF %% when present; otherwise floor counts are converted with a ${BUILDING_TOTAL_FLOORS}-floor building height. PDF only — convert Excel or slides to PDF if needed. Optional sample: make seed-construction.`}
        actions={
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-900 hover:bg-emerald-100">
            <input
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              disabled={upload.isPending}
              onChange={(e) => {
                const f = e.target.files?.[0]
                e.target.value = ''
                if (f) upload.mutate(f)
              }}
            />
            {upload.isPending ? 'Uploading…' : 'Upload PDF'}
          </label>
        }
      />

      {upload.isError ? (
        <p className="text-sm text-red-600">{String(upload.error)}</p>
      ) : null}
      {upload.data ? (
        <Panel>
          <SectionTitle>Last upload</SectionTitle>
          <p className="mt-2 text-sm text-zinc-700">
            Saved as-of <span className="font-mono">{upload.data.as_of_date}</span> —{' '}
            {upload.data.rows_parsed} rows, {upload.data.zones_parsed} zones.
          </p>
          {upload.data.parse_warnings.length > 0 ? (
            <ul className="mt-2 list-inside list-disc text-xs text-amber-800">
              {upload.data.parse_warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          ) : null}
        </Panel>
      ) : null}

      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SectionTitle>Snapshots</SectionTitle>
          <button
            type="button"
            className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-900 hover:bg-red-100 disabled:opacity-50"
            disabled={deleteAll.isPending}
            onClick={() => {
              if (
                !window.confirm(
                  'Delete all construction data? This removes every snapshot, parsed row, zone label, and project. This cannot be undone.',
                )
              ) {
                return
              }
              deleteAll.mutate()
            }}
          >
            {deleteAll.isPending ? 'Deleting…' : 'Delete all data'}
          </button>
        </div>
        {deleteAll.isError ? (
          <p className="mt-2 text-sm text-red-600">{String(deleteAll.error)}</p>
        ) : null}
        {deleteAll.data ? (
          <p className="mt-2 text-sm text-emerald-800">
            Removed {deleteAll.data.snapshots_deleted} snapshot(s),{' '}
            {deleteAll.data.zone_labels_deleted} zone label(s), {deleteAll.data.projects_deleted}{' '}
            project(s).
          </p>
        ) : null}
        {snapshots.data?.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {snapshots.data.map((s) => (
              <li key={s.id} className="flex flex-wrap gap-x-3 text-zinc-800">
                <span className="font-mono">{s.as_of_date}</span>
                <span className="text-zinc-500">{s.source_filename}</span>
                <span className="text-zinc-500">{s.row_count} rows</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-zinc-600">No reports yet. Upload a builder PDF to begin.</p>
        )}
      </Panel>

      <div>
        <SectionTitle>Tower progress</SectionTitle>
        <p className="mt-1 text-sm text-zinc-600">
          Pick a tower to see all activities for the latest report and how the tower average moves
          month on month ({BUILDING_TOTAL_FLOORS} floors assumed for floor-based %).
        </p>

        {zones.isPending ? (
          <div className="mt-4">
            <PageLoading lines={2} />
          </div>
        ) : towerZones.length === 0 ? (
          <p className="mt-4 text-sm text-zinc-600">
            No tower zones in the data yet. Upload a report or run seed-construction.
          </p>
        ) : (
          <>
            <div className="mt-4 flex flex-wrap gap-2">
              {towerZones.map((zk) => {
                const active = zoneKey === zk
                return (
                  <button
                    key={zk}
                    type="button"
                    onClick={() => setZoneKey(zk)}
                    className={
                      active
                        ? 'rounded-full border border-emerald-600 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-900 shadow-sm'
                        : 'rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50'
                    }
                  >
                    {displayZone(zk)}
                  </button>
                )
              })}
            </div>
            {sortedZones.some((z) => !z.startsWith('tower:')) ? (
              <p className="mt-2 text-xs text-zinc-500">
                Non-tower zones (e.g. landscape, clubhouse) are parsed but not shown in this tower
                view.
              </p>
            ) : null}

            <div className="mt-6 grid gap-4 lg:grid-cols-3">
              <div className="rounded-xl border border-zinc-200 bg-white p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Tower average (effective)
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900">
                  {towerDashboard.isPending
                    ? '…'
                    : fmtPct(towerDashboard.data?.latest_snapshot_avg_effective_pct ?? null)}
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  Mean of activity lines: PDF % or floors ÷ {BUILDING_TOTAL_FLOORS}.
                </p>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-white p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Tower average (floors only)
                </p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900">
                  {towerDashboard.isPending
                    ? '…'
                    : fmtPct(towerDashboard.data?.latest_snapshot_avg_floors_pct ?? null)}
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  Mean of floors ÷ {BUILDING_TOTAL_FLOORS} where floor counts exist.
                </p>
              </div>
              <div className="rounded-xl border border-zinc-200 bg-white p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Latest report
                </p>
                <p className="mt-1 font-mono text-lg font-semibold text-zinc-900">
                  {towerDashboard.isPending
                    ? '…'
                    : towerDashboard.data?.latest_as_of_date ?? '—'}
                </p>
                <p className="mt-1 text-xs text-zinc-500">
                  {towerDashboard.data?.activity_rows.length ?? 0} activities in this tower.
                </p>
              </div>
            </div>

            <div className="mt-8 grid gap-6 xl:grid-cols-2">
              <div className="min-h-[360px] rounded-xl border border-zinc-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-zinc-800">
                  All activities — effective % ({displayZone(zoneKey)})
                </h3>
                {towerDashboard.isPending ? (
                  <div className="mt-8">
                    <PageLoading lines={2} />
                  </div>
                ) : towerDashboard.isError ? (
                  <p className="mt-4 text-sm text-red-600">{String(towerDashboard.error)}</p>
                ) : barData.length === 0 ? (
                  <p className="mt-8 text-sm text-zinc-600">No rows for this tower in the latest report.</p>
                ) : (
                  <ResponsiveContainer
                    width="100%"
                    height={Math.max(360, barData.length * 32)}
                  >
                    <BarChart
                      layout="vertical"
                      data={barData}
                      margin={{ top: 8, right: 12, left: 4, bottom: 8 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" horizontal={false} />
                      <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} />
                      <YAxis
                        type="category"
                        dataKey="label"
                        width={200}
                        tick={{ fontSize: 10 }}
                        interval={0}
                      />
                      <Tooltip
                        formatter={(v) => [`${Number(v ?? 0)}%`, 'Effective %']}
                        labelFormatter={() => displayZone(zoneKey)}
                      />
                      <Bar dataKey="effective_pct" name="Effective %" fill="#059669" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </div>

              <div className="min-h-[360px] rounded-xl border border-zinc-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-zinc-800">
                  Tower trend — average % over reports
                </h3>
                {towerDashboard.isPending ? (
                  <div className="mt-8">
                    <PageLoading lines={2} />
                  </div>
                ) : towerDashboard.isError ? (
                  <p className="mt-4 text-sm text-red-600">{String(towerDashboard.error)}</p>
                ) : trendChartData.length === 0 ? (
                  <p className="mt-8 text-sm text-zinc-600">No snapshots yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height={320}>
                    <LineChart data={trendChartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                      <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                      <YAxis
                        yAxisId="pct"
                        domain={[0, 100]}
                        tick={{ fontSize: 11 }}
                        label={{ value: '%', angle: -90, position: 'insideLeft' }}
                      />
                      <Tooltip
                        formatter={(value, name) => [
                          value != null ? `${Number(value).toFixed(1)}%` : '—',
                          name === 'avgEffective' ? 'Avg effective %' : 'Avg floors %',
                        ]}
                        labelFormatter={(_, p) => {
                          const pl = p?.[0]?.payload as { as_of?: string } | undefined
                          return pl?.as_of ?? ''
                        }}
                      />
                      <Legend />
                      <Line
                        yAxisId="pct"
                        type="monotone"
                        dataKey="avgEffective"
                        name="Avg effective %"
                        stroke="#059669"
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        connectNulls
                      />
                      <Line
                        yAxisId="pct"
                        type="monotone"
                        dataKey="avgFloors"
                        name="Avg floors %"
                        stroke="#6366f1"
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {towerDashboard.data?.activity_rows.length ? (
              <Panel className="mt-8">
                <SectionTitle>
                  Latest detail — {displayZone(zoneKey)} ({towerDashboard.data.latest_as_of_date})
                </SectionTitle>
                <div className="max-h-96 overflow-auto rounded border border-zinc-100">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-zinc-50">
                      <tr>
                        <th className="p-2">Section</th>
                        <th className="p-2">Activity</th>
                        <th className="p-2">Floors</th>
                        <th className="p-2">PDF %</th>
                        <th className="p-2">Effective %</th>
                        <th className="p-2">Floors ÷ {BUILDING_TOTAL_FLOORS}</th>
                        <th className="p-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {towerDashboard.data.activity_rows.map((r, idx) => (
                        <tr key={`${r.activity_raw}-${idx}`} className="border-t border-zinc-100">
                          <td className="p-2">{r.section}</td>
                          <td className="p-2">{r.activity_raw}</td>
                          <td className="p-2">{r.floors_complete ?? '—'}</td>
                          <td className="p-2">{r.pct_reported ?? '—'}</td>
                          <td className="p-2">{r.effective_pct ?? '—'}</td>
                          <td className="p-2">{r.floors_pct_of_total ?? '—'}</td>
                          <td className="p-2">{r.status ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            ) : null}
          </>
        )}

        <button
          type="button"
          className="mt-4 text-xs font-medium text-emerald-800 underline"
          onClick={() => setShowLabels(true)}
        >
          Edit zone display names
        </button>
      </div>

      {showLabels ? (
        <Panel>
          <SectionTitle>Zone display names</SectionTitle>
          {zoneLabels.isPending ? (
            <PageLoading lines={2} />
          ) : (
            <>
              <p className="mb-3 mt-2 text-xs text-zinc-600">
                Default names follow tower order (1–12, then 14, 15, …). Override labels for charts
                and buttons.
              </p>
              <div className="max-h-72 space-y-2 overflow-y-auto">
                {Object.keys(labelDraft)
                  .sort()
                  .map((zk) => (
                    <div key={zk} className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="w-32 shrink-0 font-mono text-xs text-zinc-500">{zk}</span>
                      <input
                        className="min-w-[12rem] flex-1 rounded-md border border-zinc-200 px-2 py-1"
                        value={labelDraft[zk] ?? ''}
                        onChange={(e) =>
                          setLabelDraft((d) => ({ ...d, [zk]: e.target.value }))
                        }
                      />
                    </div>
                  ))}
              </div>
              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                  disabled={saveLabels.isPending}
                  onClick={() => saveLabels.mutate()}
                >
                  {saveLabels.isPending ? 'Saving…' : 'Save labels'}
                </button>
                <button
                  type="button"
                  className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-700"
                  onClick={() => setShowLabels(false)}
                >
                  Close
                </button>
              </div>
            </>
          )}
        </Panel>
      ) : null}
    </div>
  )
}
