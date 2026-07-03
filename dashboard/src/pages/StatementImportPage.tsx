import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  createStatementImportRule,
  deleteStatementImportRule,
  downloadStatementImportCsv,
  fetchLatestStatementImportSnapshot,
  fetchStatementImportGmailStatus,
  fetchStatementImportRules,
  fetchStatementImportTags,
  fetchStatementsImportNow,
  putStatementImportTags,
  updateStatementImportRule,
} from '@/lib/api'
import type {
  StatementImportRuleBody,
  StatementImportRuleOut,
  StatementImportTransactionRow,
  StatementTagRuleBody,
} from '@/types/api'

type RuleDraft = StatementImportRuleBody & { id?: number }

const EMPTY_RULE: RuleDraft = {
  bank: '',
  card: '',
  from_emails: [''],
  subject_contains: '',
  pdf_password: '',
  is_enabled: true,
}

function parseEmailsInput(raw: string): string[] {
  return raw
    .split(/[,;\n]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function formatAmount(amount: number): string {
  const sign = amount < 0 ? '-' : ''
  return `${sign}₹${Math.abs(amount).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function StatementImportPage() {
  const qc = useQueryClient()
  const [ruleDraft, setRuleDraft] = useState<RuleDraft | null>(null)
  const [tagDrafts, setTagDrafts] = useState<StatementTagRuleBody[] | null>(null)
  const [periodFilter, setPeriodFilter] = useState<string>('all')

  const qGmail = useQuery({
    queryKey: ['statement-import-gmail'],
    queryFn: fetchStatementImportGmailStatus,
  })
  const qRules = useQuery({
    queryKey: ['statement-import-rules'],
    queryFn: fetchStatementImportRules,
  })
  const qTags = useQuery({
    queryKey: ['statement-import-tags'],
    queryFn: fetchStatementImportTags,
  })
  const qSnapshot = useQuery({
    queryKey: ['statement-import-snapshot'],
    queryFn: fetchLatestStatementImportSnapshot,
  })

  const fetchMut = useMutation({
    mutationFn: fetchStatementsImportNow,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['statement-import-snapshot'] })
    },
  })

  const saveRuleMut = useMutation({
    mutationFn: async (draft: RuleDraft) => {
      const body: StatementImportRuleBody = {
        bank: draft.bank.trim(),
        card: draft.card.trim(),
        from_emails: draft.from_emails.filter(Boolean),
        subject_contains: draft.subject_contains?.trim() || null,
        pdf_password: draft.pdf_password?.trim() || null,
        credit_card_id: draft.credit_card_id ?? null,
        is_enabled: draft.is_enabled ?? true,
      }
      if (draft.id) {
        return updateStatementImportRule(draft.id, body)
      }
      return createStatementImportRule(body)
    },
    onSuccess: () => {
      setRuleDraft(null)
      void qc.invalidateQueries({ queryKey: ['statement-import-rules'] })
    },
  })

  const deleteRuleMut = useMutation({
    mutationFn: deleteStatementImportRule,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['statement-import-rules'] })
    },
  })

  const saveTagsMut = useMutation({
    mutationFn: (tags: StatementTagRuleBody[]) => putStatementImportTags(tags),
    onSuccess: () => {
      setTagDrafts(null)
      void qc.invalidateQueries({ queryKey: ['statement-import-tags'] })
    },
  })

  const csvMut = useMutation({
    mutationFn: downloadStatementImportCsv,
  })

  const transactions: StatementImportTransactionRow[] = useMemo(() => {
    if (fetchMut.data?.transactions?.length) return fetchMut.data.transactions
    return qSnapshot.data?.transactions ?? []
  }, [fetchMut.data, qSnapshot.data])

  const periods = useMemo(() => {
    const set = new Set(transactions.map((t) => t.statement_period).filter(Boolean))
    return ['all', ...Array.from(set).sort().reverse()]
  }, [transactions])

  const filteredTx = useMemo(() => {
    if (periodFilter === 'all') return transactions
    return transactions.filter((t) => t.statement_period === periodFilter)
  }, [transactions, periodFilter])

  if (qGmail.isPending || qRules.isPending || qTags.isPending) return <PageLoading />
  if (qGmail.isError || qRules.isError || qTags.isError) {
    return <PageError title="Error" message="Could not load statement import settings." />
  }

  const gmailOk = qGmail.data?.configured ?? false
  const rules = qRules.data ?? []
  const tags = tagDrafts ?? (qTags.data ?? []).map((t) => ({
    tag_name: t.tag_name,
    regex_patterns: t.regex_patterns,
    is_enabled: t.is_enabled,
  }))
  const enabledRules = rules.filter((r) => r.is_enabled)

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Import"
        title="Statement import"
        description="Fetch credit card statement PDFs from Gmail, parse with bank-specific parsers, and preview transactions. Configure sender rules and tags below."
        actions={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => csvMut.mutate()}
              disabled={csvMut.isPending || transactions.length === 0}
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50 disabled:opacity-50"
            >
              {csvMut.isPending ? 'Downloading…' : 'Download CSV'}
            </button>
            <button
              type="button"
              onClick={() => fetchMut.mutate()}
              disabled={fetchMut.isPending || !gmailOk || enabledRules.length === 0}
              className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {fetchMut.isPending ? 'Fetching…' : 'Fetch statements'}
            </button>
          </div>
        }
      />

      <section>
        <SectionTitle>Gmail connection</SectionTitle>
        <Panel>
          {gmailOk ? (
            <p className="text-sm text-emerald-700">
              Gmail OAuth is configured. Statements are fetched via the Gmail API (not IMAP).
            </p>
          ) : (
            <p className="text-sm text-amber-800">
              Gmail is not configured. Set <code className="rounded bg-zinc-100 px-1">GMAIL_CREDENTIALS_PATH</code>{' '}
              in your API <code className="rounded bg-zinc-100 px-1">.env</code> and run{' '}
              <code className="rounded bg-zinc-100 px-1">scripts/setup_gmail.py</code>.
            </p>
          )}
        </Panel>
      </section>

      {fetchMut.isError ? (
        <p className="text-sm text-red-600">{String(fetchMut.error)}</p>
      ) : null}
      {fetchMut.isSuccess ? (
        <p className="text-sm text-emerald-700">
          Scanned {fetchMut.data.gmail_scanned} email(s) · parsed {fetchMut.data.statements_parsed}{' '}
          statement(s) · {fetchMut.data.transactions.length} transaction row(s) · skipped{' '}
          {fetchMut.data.skipped.length}.
        </p>
      ) : null}

      <section>
        <SectionTitle>Card rules</SectionTitle>
        <p className="mb-3 text-sm text-zinc-600">
          One rule per bank/card: sender addresses, optional subject filter, and PDF password.
        </p>
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-zinc-600">
                  <th className="py-2 pr-3 font-medium">Bank</th>
                  <th className="py-2 pr-3 font-medium">Card</th>
                  <th className="py-2 pr-3 font-medium">From emails</th>
                  <th className="py-2 pr-3 font-medium">Subject contains</th>
                  <th className="py-2 pr-3 font-medium">PDF password</th>
                  <th className="py-2 pr-3 font-medium">On</th>
                  <th className="py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r: StatementImportRuleOut) => (
                  <tr key={r.id} className="border-b border-zinc-100">
                    <td className="py-2 pr-3 font-medium">{r.bank}</td>
                    <td className="py-2 pr-3">{r.card}</td>
                    <td className="py-2 pr-3 text-xs text-zinc-600">{r.from_emails.join(', ')}</td>
                    <td className="py-2 pr-3 text-xs text-zinc-600">{r.subject_contains ?? '—'}</td>
                    <td className="py-2 pr-3 text-xs">{r.pdf_password ? '••••' : '—'}</td>
                    <td className="py-2 pr-3">{r.is_enabled ? 'Yes' : 'No'}</td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        className="mr-2 text-emerald-700 hover:underline"
                        onClick={() =>
                          setRuleDraft({
                            id: r.id,
                            bank: r.bank,
                            card: r.card,
                            from_emails: r.from_emails,
                            subject_contains: r.subject_contains ?? '',
                            pdf_password: r.pdf_password ?? '',
                            credit_card_id: r.credit_card_id,
                            is_enabled: r.is_enabled,
                          })
                        }
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="text-red-600 hover:underline"
                        onClick={() => deleteRuleMut.mutate(r.id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="mt-4 rounded-lg border border-dashed border-zinc-300 px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
            onClick={() => setRuleDraft({ ...EMPTY_RULE })}
          >
            + Add card rule
          </button>

          {ruleDraft ? (
            <div className="mt-6 space-y-3 rounded-xl border border-zinc-200 bg-zinc-50/80 p-4">
              <h3 className="text-sm font-semibold text-zinc-900">
                {ruleDraft.id ? 'Edit rule' : 'New rule'}
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-xs font-medium text-zinc-600">
                  Bank
                  <input
                    className="mt-1 w-full rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                    value={ruleDraft.bank}
                    onChange={(e) => setRuleDraft({ ...ruleDraft, bank: e.target.value })}
                    placeholder="ICICI"
                  />
                </label>
                <label className="block text-xs font-medium text-zinc-600">
                  Card label
                  <input
                    className="mt-1 w-full rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                    value={ruleDraft.card}
                    onChange={(e) => setRuleDraft({ ...ruleDraft, card: e.target.value })}
                  />
                </label>
              </div>
              <label className="block text-xs font-medium text-zinc-600">
                From emails (comma-separated)
                <input
                  className="mt-1 w-full rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                  value={ruleDraft.from_emails.join(', ')}
                  onChange={(e) =>
                    setRuleDraft({ ...ruleDraft, from_emails: parseEmailsInput(e.target.value) })
                  }
                />
              </label>
              <label className="block text-xs font-medium text-zinc-600">
                Subject contains
                <input
                  className="mt-1 w-full rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                  value={ruleDraft.subject_contains ?? ''}
                  onChange={(e) => setRuleDraft({ ...ruleDraft, subject_contains: e.target.value })}
                />
              </label>
              <label className="block text-xs font-medium text-zinc-600">
                PDF password
                <input
                  type="password"
                  className="mt-1 w-full max-w-xs rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                  value={ruleDraft.pdf_password ?? ''}
                  onChange={(e) => setRuleDraft({ ...ruleDraft, pdf_password: e.target.value })}
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-zinc-700">
                <input
                  type="checkbox"
                  checked={ruleDraft.is_enabled ?? true}
                  onChange={(e) => setRuleDraft({ ...ruleDraft, is_enabled: e.target.checked })}
                />
                Enabled for fetch
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={saveRuleMut.isPending}
                  onClick={() => saveRuleMut.mutate(ruleDraft)}
                  className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  type="button"
                  onClick={() => setRuleDraft(null)}
                  className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-700 hover:bg-white"
                >
                  Cancel
                </button>
              </div>
              {saveRuleMut.isError ? (
                <p className="text-sm text-red-600">{String(saveRuleMut.error)}</p>
              ) : null}
            </div>
          ) : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Tag rules</SectionTitle>
        <p className="mb-3 text-sm text-zinc-600">
          Regex patterns matched against transaction descriptions (one pattern per line).
        </p>
        <Panel>
          <div className="space-y-4">
            {tags.map((tag, idx) => (
              <div key={`${tag.tag_name}-${idx}`} className="grid gap-2 sm:grid-cols-[160px_1fr_auto]">
                <input
                  className="rounded-md border border-zinc-200 px-2 py-1.5 text-sm font-medium"
                  value={tag.tag_name}
                  onChange={(e) => {
                    const next = [...tags]
                    next[idx] = { ...tag, tag_name: e.target.value }
                    setTagDrafts(next)
                  }}
                  placeholder="TAG_NAME"
                />
                <textarea
                  className="min-h-[72px] rounded-md border border-zinc-200 px-2 py-1.5 font-mono text-xs"
                  value={tag.regex_patterns.join('\n')}
                  onChange={(e) => {
                    const next = [...tags]
                    next[idx] = {
                      ...tag,
                      regex_patterns: e.target.value.split('\n').map((l) => l.trim()).filter(Boolean),
                    }
                    setTagDrafts(next)
                  }}
                />
                <label className="flex items-center gap-1 text-xs text-zinc-600">
                  <input
                    type="checkbox"
                    checked={tag.is_enabled ?? true}
                    onChange={(e) => {
                      const next = [...tags]
                      next[idx] = { ...tag, is_enabled: e.target.checked }
                      setTagDrafts(next)
                    }}
                  />
                  On
                </label>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-lg border border-dashed border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50"
              onClick={() =>
                setTagDrafts([
                  ...tags,
                  { tag_name: 'NEW_TAG', regex_patterns: ['pattern'], is_enabled: true },
                ])
              }
            >
              + Add tag
            </button>
            <button
              type="button"
              disabled={saveTagsMut.isPending}
              onClick={() => saveTagsMut.mutate(tags)}
              className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              Save tags
            </button>
          </div>
        </Panel>
      </section>

      <section>
        <SectionTitle>Parsed transactions</SectionTitle>
        {qSnapshot.data && !fetchMut.isSuccess ? (
          <p className="mb-2 text-xs text-zinc-500">
            Last fetch: {qSnapshot.data.fetched_at} · {qSnapshot.data.statements_parsed}{' '}
            statement(s) · {transactions.length} row(s)
          </p>
        ) : null}
        <Panel variant="table">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <label className="text-xs text-zinc-600">
              Statement month
              <select
                className="ml-2 rounded-md border border-zinc-200 px-2 py-1 text-sm"
                value={periodFilter}
                onChange={(e) => setPeriodFilter(e.target.value)}
              >
                {periods.map((p) => (
                  <option key={p} value={p}>
                    {p === 'all' ? 'All months' : p}
                  </option>
                ))}
              </select>
            </label>
            <span className="text-xs text-zinc-500">{filteredTx.length} row(s)</span>
          </div>
          {filteredTx.length === 0 ? (
            <p className="py-8 text-center text-sm text-zinc-500">
              No transactions yet. Configure card rules and click Fetch statements.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[960px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-zinc-600">
                    <th className="py-2 pr-3 font-medium">Date</th>
                    <th className="py-2 pr-3 font-medium">Bank / Card</th>
                    <th className="py-2 pr-3 font-medium">Description</th>
                    <th className="py-2 pr-3 font-medium text-right">Amount</th>
                    <th className="py-2 pr-3 font-medium">Category</th>
                    <th className="py-2 pr-3 font-medium">Tags</th>
                    <th className="py-2 font-medium">Period</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTx.map((t, i) => (
                    <tr key={`${t.gmail_message_id}-${t.date}-${i}`} className="border-b border-zinc-100">
                      <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs">{t.date}</td>
                      <td className="py-2 pr-3 text-xs">
                        {t.bank}
                        <br />
                        <span className="text-zinc-500">{t.card}</span>
                      </td>
                      <td className="max-w-[280px] truncate py-2 pr-3" title={t.description}>
                        {t.description}
                      </td>
                      <td
                        className={`whitespace-nowrap py-2 pr-3 text-right font-mono text-xs ${
                          t.amount < 0 ? 'text-emerald-700' : 'text-zinc-900'
                        }`}
                      >
                        {formatAmount(t.amount)}
                      </td>
                      <td className="py-2 pr-3 text-xs text-zinc-600">{t.category ?? '—'}</td>
                      <td className="py-2 pr-3 text-xs text-zinc-600">{t.tags || '—'}</td>
                      <td className="py-2 font-mono text-xs text-zinc-500">{t.statement_period}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </section>
    </div>
  )
}
