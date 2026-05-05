import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { fetchSettings, putSettings } from '@/lib/api'


export function SettingsPage() {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  })

  const [fyDraft, setFyDraft] = useState<string | null>(null)
  const fy = useMemo(() => fyDraft ?? q.data?.current_fy ?? '', [fyDraft, q.data?.current_fy])

  const save = useMutation({
    mutationFn: () => putSettings({ current_fy: fy.trim() }),
    onSuccess: () => {
      setFyDraft(null)
      void qc.invalidateQueries({ queryKey: ['settings'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      void qc.invalidateQueries({ queryKey: ['fy-spending'] })
      void qc.invalidateQueries({ queryKey: ['fy-summary'] })
    },
  })

  if (q.isPending) {
    return <PageLoading lines={2} />
  }

  if (q.isError) {
    return (
      <PageError title="Could not load settings" message={<p className="text-sm">{String(q.error)}</p>} />
    )
  }

  return (
    <div className="max-w-xl space-y-10">
      <PageHero
        eyebrow="Workspace"
        title="Settings"
        description="Financial year drives budgets and reports (April–March Indian FY)."
      />

      <section>
        <SectionTitle>Financial year</SectionTitle>
        <Panel>
        <h2 className="sr-only">Financial year</h2>
        <p className="mt-2 text-xs text-zinc-500">
          Format <code className="rounded bg-zinc-100 px-1">YYYY-YY</code> e.g.{' '}
          <span className="font-mono">2025-26</span> for Apr 2025 – Mar 2026.
        </p>
        <label className="mt-4 block text-xs font-medium text-zinc-600">
          Current FY
          <input
            className="mt-1 block w-full max-w-xs rounded-md border border-zinc-200 px-3 py-2 font-mono text-sm text-zinc-900"
            value={fy}
            onChange={(e) => setFyDraft(e.target.value)}
            aria-label="Current financial year"
          />
        </label>
        <button
          type="button"
          disabled={save.isPending}
          onClick={() => save.mutate()}
          className="mt-4 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
        >
          Save
        </button>
        {save.isError ? <p className="mt-2 text-sm text-red-700">{String(save.error)}</p> : null}
        </Panel>
      </section>

      <section className="rounded-2xl border border-dashed border-emerald-200/60 bg-gradient-to-br from-emerald-50/40 via-zinc-50/80 to-zinc-50 p-6 text-sm text-zinc-600 shadow-sm ring-1 ring-emerald-900/[0.05]">
        <p className="font-medium text-zinc-800">Tax & income streams</p>
        <p className="mt-2">
          Configure multiple income streams and tax regime on the{' '}
          <span className="font-medium text-zinc-900">Income & tax</span> page. Amounts stay in your
          local SQLite database.
        </p>
      </section>
    </div>
  )
}
