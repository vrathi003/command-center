import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  fetchCreditCardStatementsNow,
  fetchCreditCards,
  fetchRecentCreditCardStatements,
  putCreditCard,
} from '@/lib/api'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import type { CreditCardOut } from '@/types/api'

export function CreditCardStatementInboxPage() {
  const qc = useQueryClient()
  const [passwordDrafts, setPasswordDrafts] = useState<Record<number, string>>({})

  const qCards = useQuery({ queryKey: ['credit-cards'], queryFn: () => fetchCreditCards() })
  const qStatements = useQuery({
    queryKey: ['credit-card-statements', 'recent'],
    queryFn: () => fetchRecentCreditCardStatements(50),
  })

  const cardNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const c of qCards.data ?? []) m.set(c.id, c.name)
    return m
  }, [qCards.data])

  const fetchNowMut = useMutation({
    mutationFn: fetchCreditCardStatementsNow,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['credit-card-statements', 'recent'] })
    },
  })

  const toggleMut = useMutation({
    mutationFn: (p: { id: number; auto_fetch_enabled: boolean }) =>
      putCreditCard(p.id, { auto_fetch_enabled: p.auto_fetch_enabled }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['credit-cards'] })
    },
  })

  const savePasswordMut = useMutation({
    mutationFn: (p: { id: number; statement_pdf_password: string | null }) =>
      putCreditCard(p.id, { statement_pdf_password: p.statement_pdf_password }),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['credit-cards'] })
      setPasswordDrafts((prev) => {
        const next = { ...prev }
        delete next[vars.id]
        return next
      })
    },
  })

  if (qCards.isLoading || qStatements.isLoading) return <PageLoading />
  if (qCards.isError || qStatements.isError) {
    return <PageError title="Error" message="Could not load statement inbox." />
  }

  const cards = qCards.data ?? []
  const statements = qStatements.data ?? []

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Borrowing"
        title="Statement inbox"
        description="Auto-fetch credit-card statement PDFs from Gmail by card, review parsed line items, and import — same review step as manual upload."
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              to="/credit-cards"
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50"
            >
              Back to cards
            </Link>
            <button
              type="button"
              onClick={() => fetchNowMut.mutate()}
              disabled={fetchNowMut.isPending}
              className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {fetchNowMut.isPending ? 'Fetching…' : 'Fetch now'}
            </button>
          </div>
        }
      />

      {fetchNowMut.isError ? (
        <p className="text-sm text-red-600">{String(fetchNowMut.error)}</p>
      ) : null}
      {fetchNowMut.isSuccess ? (
        <p className="text-sm text-emerald-700">
          Scanned {fetchNowMut.data.fetched} email(s) · staged {fetchNowMut.data.staged} new
          statement(s) · skipped {fetchNowMut.data.skipped_unmatched} unmatched,{' '}
          {fetchNowMut.data.skipped_duplicate} already seen.
        </p>
      ) : null}

      <section>
        <SectionTitle>Per-card auto-fetch settings</SectionTitle>
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-zinc-600">
                  <th className="py-2 pr-3 font-medium">Card</th>
                  <th className="py-2 pr-3 font-medium">Auto-fetch</th>
                  <th className="py-2 pr-3 font-medium">Statement PDF password</th>
                  <th className="py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {cards.map((c: CreditCardOut) => (
                  <tr key={c.id} className="border-b border-zinc-100">
                    <td className="py-2 pr-3 font-medium text-zinc-900">{c.name}</td>
                    <td className="py-2 pr-3">
                      <input
                        type="checkbox"
                        checked={c.auto_fetch_enabled}
                        onChange={(e) =>
                          toggleMut.mutate({ id: c.id, auto_fetch_enabled: e.target.checked })
                        }
                      />
                    </td>
                    <td className="py-2 pr-3">
                      <input
                        type="password"
                        value={passwordDrafts[c.id] ?? c.statement_pdf_password ?? ''}
                        onChange={(e) =>
                          setPasswordDrafts((prev) => ({ ...prev, [c.id]: e.target.value }))
                        }
                        placeholder="none"
                        className="w-full max-w-[220px] rounded-lg border border-zinc-200 px-2 py-1 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      />
                    </td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        onClick={() =>
                          savePasswordMut.mutate({
                            id: c.id,
                            statement_pdf_password: (passwordDrafts[c.id] ?? '').trim() || null,
                          })
                        }
                        disabled={!(c.id in passwordDrafts) || savePasswordMut.isPending}
                        className="text-emerald-700 hover:underline disabled:opacity-40"
                      >
                        Save
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {cards.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-600">No credit cards yet.</p>
            ) : null}
          </div>
        </Panel>
      </section>

      <section>
        <SectionTitle>
          {statements.length} recent statement{statements.length !== 1 ? 's' : ''}
        </SectionTitle>
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-zinc-600">
                  <th className="py-2 pr-3 font-medium">Card</th>
                  <th className="py-2 pr-3 font-medium">Filename</th>
                  <th className="py-2 pr-3 font-medium">Period</th>
                  <th className="py-2 pr-3 font-medium">Source</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {statements.map((s) => (
                  <tr key={s.id} className="border-b border-zinc-100">
                    <td className="py-2 pr-3 font-medium text-zinc-900">
                      {cardNameById.get(s.credit_card_id) ?? `#${s.credit_card_id}`}
                    </td>
                    <td className="py-2 pr-3 text-zinc-700">{s.filename}</td>
                    <td className="py-2 pr-3 text-zinc-700">
                      {s.period_start ?? '—'} – {s.period_end ?? '—'}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                          s.source === 'auto_fetch'
                            ? 'bg-violet-100 text-violet-800'
                            : 'bg-zinc-100 text-zinc-600'
                        }`}
                      >
                        {s.source === 'auto_fetch' ? 'auto-fetch' : 'upload'}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium ${
                          s.status === 'applied'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {s.status}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <Link
                        to={`/credit-cards/${s.credit_card_id}/statements/${s.id}`}
                        className="text-emerald-700 hover:underline"
                      >
                        Review
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {statements.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-600">
                No statements yet — click "Fetch now" or upload one from a card's page.
              </p>
            ) : null}
          </div>
        </Panel>
      </section>
    </div>
  )
}
