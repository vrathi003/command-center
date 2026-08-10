import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  applyLegacyLedgerMigration,
  dryRunLegacyLedgerMigration,
  fetchSettings,
  putSettings,
} from '@/lib/api'


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
  const dryRun = useMutation({
    mutationFn: dryRunLegacyLedgerMigration,
  })
  const applyMigration = useMutation({
    mutationFn: applyLegacyLedgerMigration,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['settings'] })
      void qc.invalidateQueries({ queryKey: ['transactions'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })
  const migrationReport = applyMigration.data ?? dryRun.data
  const cutoverAt = q.data?.project_config.legacy_cutover_at ?? migrationReport?.cutover_at

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

      <section>
        <SectionTitle>Ledger migration</SectionTitle>
        <Panel>
          <h2 className="sr-only">Ledger migration</h2>
          <p className="mt-2 text-sm text-zinc-600">
            Preview or migrate legacy transactions to the double-entry ledger. Applying creates a
            database backup and archives the legacy history.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={dryRun.isPending || applyMigration.isPending}
              onClick={() => dryRun.mutate()}
              className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-50"
            >
              {dryRun.isPending ? 'Running preview…' : 'Dry-run'}
            </button>
            <button
              type="button"
              disabled={dryRun.isPending || applyMigration.isPending || Boolean(cutoverAt)}
              onClick={() => {
                if (
                  window.confirm(
                    'Apply the legacy-to-ledger migration? This will back up the database and archive legacy transaction history.',
                  )
                ) {
                  applyMigration.mutate()
                }
              }}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {applyMigration.isPending ? 'Applying migration…' : 'Apply'}
            </button>
          </div>
          {dryRun.isError ? <p className="mt-3 text-sm text-red-700">{String(dryRun.error)}</p> : null}
          {applyMigration.isError ? (
            <p className="mt-3 text-sm text-red-700">{String(applyMigration.error)}</p>
          ) : null}
          {migrationReport ? (
            <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-zinc-500">Migrated</dt>
                <dd className="font-semibold text-zinc-900">{migrationReport.migrated}</dd>
              </div>
              <div>
                <dt className="text-zinc-500">Quarantined</dt>
                <dd className="font-semibold text-zinc-900">{migrationReport.quarantined}</dd>
              </div>
              <div>
                <dt className="text-zinc-500">Skipped deleted</dt>
                <dd className="font-semibold text-zinc-900">{migrationReport.skipped_deleted}</dd>
              </div>
              <div>
                <dt className="text-zinc-500">No-op</dt>
                <dd className="font-semibold text-zinc-900">{migrationReport.noop}</dd>
              </div>
            </dl>
          ) : null}
          {cutoverAt ? (
            <p className="mt-5 text-sm text-emerald-800">
              Ledger cutover completed{' '}
              <time dateTime={cutoverAt}>{new Date(cutoverAt).toLocaleString()}</time>.
            </p>
          ) : null}
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
