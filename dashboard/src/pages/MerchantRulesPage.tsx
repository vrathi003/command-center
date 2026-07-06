import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Plus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { MANUAL_TX_CATEGORIES } from '@/constants/transactionForm'
import {
  deleteMerchantRule,
  fetchMerchantRules,
  fetchUncategorizedMerchants,
  postClassifyConfirm,
  postClassifySuggest,
  postMerchantRule,
  putMerchantRule,
  type MerchantRuleBody,
} from '@/lib/api'
import { formatPaise } from '@/lib/format'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { Panel } from '@/components/ui/Panel'
import type { LlmSuggestionOut, MerchantRuleOut } from '@/types/api'

const BLANK = {
  match_type: 'contains' as 'exact' | 'contains',
  match_value: '',
  canonical_merchant: '',
  merchant_type: '',
  category: '',
}

function toBody(f: typeof BLANK): MerchantRuleBody {
  return {
    match_type: f.match_type,
    match_value: f.match_value.trim(),
    canonical_merchant: f.canonical_merchant.trim(),
    merchant_type: f.merchant_type.trim() || null,
    category: f.category,
    source: 'user',
  }
}

type ReviewRow = LlmSuggestionOut & { checked: boolean }

export function MerchantRulesPage() {
  const qc = useQueryClient()
  const [form, setForm] = useState(BLANK)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<'rules' | 'review'>('rules')
  const [ruleSearch, setRuleSearch] = useState('')
  const [reviewSearch, setReviewSearch] = useState('')
  const [lastApplied, setLastApplied] = useState<{ ledger: number; statement: number } | null>(
    null,
  )
  const [selectedMerchants, setSelectedMerchants] = useState<Set<string>>(new Set())
  const [review, setReview] = useState<ReviewRow[] | null>(null)
  const [aiError, setAiError] = useState<string | null>(null)

  const qRules = useQuery({ queryKey: ['merchant-rules'], queryFn: () => fetchMerchantRules() })
  const qUncategorized = useQuery({
    queryKey: ['merchant-rules', 'uncategorized'],
    queryFn: fetchUncategorizedMerchants,
  })

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ['merchant-rules'] })
    qc.invalidateQueries({ queryKey: ['transactions'] })
    qc.invalidateQueries({ queryKey: ['statement-import-snapshot'] })
  }

  const createMut = useMutation({
    mutationFn: postMerchantRule,
    onSuccess: (r) => {
      invalidateAll()
      setForm(BLANK)
      setFormError(null)
      setFormOpen(false)
      setEditingId(null)
      setLastApplied({
        ledger: r.retroactively_applied ?? 0,
        statement: r.statement_import_applied ?? 0,
      })
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: MerchantRuleBody }) =>
      putMerchantRule(id, body),
    onSuccess: (r) => {
      invalidateAll()
      setEditingId(null)
      setForm(BLANK)
      setFormError(null)
      setFormOpen(false)
      setLastApplied({
        ledger: r.retroactively_applied ?? 0,
        statement: r.statement_import_applied ?? 0,
      })
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: deleteMerchantRule,
    onSuccess: () => invalidateAll(),
  })

  const suggestMut = useMutation({
    mutationFn: postClassifySuggest,
    onSuccess: (suggestions) => {
      setAiError(null)
      setReview(suggestions.map((s) => ({ ...s, checked: s.confidence >= 0.8 })))
    },
    onError: (e: Error) => setAiError(e.message),
  })

  const confirmMut = useMutation({
    mutationFn: postClassifyConfirm,
    onSuccess: (r) => {
      invalidateAll()
      qc.invalidateQueries({ queryKey: ['merchant-rules', 'uncategorized'] })
      setReview(null)
      setSelectedMerchants(new Set())
      setLastApplied({
        ledger: r.total_retroactively_applied,
        statement: r.total_statement_import_applied ?? 0,
      })
    },
    onError: (e: Error) => setAiError(e.message),
  })

  const startEdit = (r: MerchantRuleOut) => {
    setEditingId(r.id)
    setForm({
      match_type: r.match_type,
      match_value: r.match_value,
      canonical_merchant: r.canonical_merchant,
      merchant_type: r.merchant_type ?? '',
      category: r.category,
    })
    setFormError(null)
    setFormOpen(true)
    setActiveTab('rules')
  }

  const cancelEdit = () => {
    setEditingId(null)
    setForm(BLANK)
    setFormError(null)
    setFormOpen(false)
  }

  const openNewRule = () => {
    setEditingId(null)
    setForm(BLANK)
    setFormError(null)
    setFormOpen(true)
    setActiveTab('rules')
  }

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setLastApplied(null)
    if (!form.match_value.trim() || !form.canonical_merchant.trim() || !form.category) {
      setFormError('Match value, canonical merchant, and category are required.')
      return
    }
    const body = toBody(form)
    if (editingId !== null) {
      updateMut.mutate({ id: editingId, body })
    } else {
      createMut.mutate(body)
    }
  }

  const prefillFromUncategorized = (merchant: string) => {
    setEditingId(null)
    setForm({
      match_type: 'exact',
      match_value: merchant,
      canonical_merchant: merchant,
      merchant_type: '',
      category: '',
    })
    setFormError(null)
    setFormOpen(true)
    setActiveTab('rules')
  }

  const toggleSelected = (merchant: string) => {
    setSelectedMerchants((prev) => {
      const next = new Set(prev)
      if (next.has(merchant)) next.delete(merchant)
      else next.add(merchant)
      return next
    })
  }

  const runClassifyWithAi = () => {
    const merchants = Array.from(selectedMerchants)
    if (merchants.length === 0) return
    setAiError(null)
    suggestMut.mutate(merchants)
  }

  const toggleReviewChecked = (i: number) => {
    setReview((prev) =>
      prev ? prev.map((r, idx) => (idx === i ? { ...r, checked: !r.checked } : r)) : prev,
    )
  }

  const updateReviewField = (i: number, field: 'canonical_merchant' | 'category', value: string) => {
    setReview((prev) =>
      prev ? prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)) : prev,
    )
  }

  const confirmSelected = () => {
    if (!review) return
    const chosen = review.filter((r) => r.checked)
    if (chosen.length === 0) return
    confirmMut.mutate(
      chosen.map((r) => ({
        raw_merchant: r.raw_merchant,
        match_type: 'exact' as const,
        canonical_merchant: r.canonical_merchant,
        merchant_type: r.merchant_type,
        category: r.category,
      })),
    )
  }

  const rules = qRules.data ?? []
  const uncategorized = qUncategorized.data ?? []
  const busy = createMut.isPending || updateMut.isPending

  const filteredRules = useMemo(() => {
    const q = ruleSearch.trim().toLowerCase()
    if (!q) return rules
    return rules.filter(
      (r) =>
        r.match_value.toLowerCase().includes(q) ||
        r.canonical_merchant.toLowerCase().includes(q) ||
        r.category.toLowerCase().includes(q),
    )
  }, [rules, ruleSearch])

  const filteredReview = useMemo(() => {
    const q = reviewSearch.trim().toLowerCase()
    if (!q) return uncategorized
    return uncategorized.filter((g) => g.merchant.toLowerCase().includes(q))
  }, [uncategorized, reviewSearch])

  if (qRules.isLoading || qUncategorized.isLoading) return <PageLoading />
  if (qRules.isError) return <PageError title="Error" message="Could not load merchant rules." />

  return (
    <div className="flex h-[calc(100dvh-3rem)] flex-col gap-2 lg:h-[calc(100dvh-4rem)]">
      <div className="shrink-0 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-900">Merchants</h1>
            <p className="text-xs text-zinc-500">
              Global mapping for imports, CC statements, Gmail & Discord · {rules.length} rule
              {rules.length !== 1 ? 's' : ''}
              {uncategorized.length > 0 ? ` · ${uncategorized.length} to review` : ''}
            </p>
          </div>
          <Link
            to="/transactions"
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
          >
            Transactions
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200/80 bg-white px-3 py-2 shadow-sm ring-1 ring-zinc-900/[0.03]">
          <button
            type="button"
            onClick={() => setActiveTab('rules')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              activeTab === 'rules' ? 'bg-emerald-100 text-emerald-900' : 'text-zinc-600 hover:bg-zinc-100'
            }`}
          >
            Rules ({rules.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('review')}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              activeTab === 'review' ? 'bg-emerald-100 text-emerald-900' : 'text-zinc-600 hover:bg-zinc-100'
            }`}
          >
            Review ({uncategorized.length})
          </button>

          <span className="hidden h-4 w-px bg-zinc-200 sm:block" aria-hidden />

          <input
            type="search"
            value={activeTab === 'rules' ? ruleSearch : reviewSearch}
            onChange={(e) =>
              activeTab === 'rules'
                ? setRuleSearch(e.target.value)
                : setReviewSearch(e.target.value)
            }
            placeholder={activeTab === 'rules' ? 'Search rules…' : 'Search merchants…'}
            className="min-w-[8rem] flex-1 rounded-md border border-zinc-200 px-2 py-1 text-xs sm:max-w-[14rem]"
          />

          {activeTab === 'rules' ? (
            <button
              type="button"
              onClick={() => (formOpen && !editingId ? cancelEdit() : openNewRule())}
              className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700"
            >
              {formOpen && !editingId ? (
                <>
                  <ChevronDown className="size-3.5 rotate-180" aria-hidden />
                  Close
                </>
              ) : (
                <>
                  <Plus className="size-3.5" aria-hidden />
                  Add rule
                </>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={runClassifyWithAi}
              disabled={selectedMerchants.size === 0 || suggestMut.isPending}
              className="rounded-md bg-violet-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-50"
            >
              {suggestMut.isPending ? 'Classifying…' : `AI classify (${selectedMerchants.size})`}
            </button>
          )}
        </div>

        {formOpen ? (
          <Panel padding={false}>
            <form onSubmit={onSubmit} className="space-y-2 p-3">
              <p className="text-xs font-medium text-zinc-700">
                {editingId !== null ? 'Edit rule' : 'New rule'}
              </p>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
                <label className="flex flex-col gap-0.5 text-xs text-zinc-600">
                  Match type
                  <select
                    value={form.match_type}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, match_type: e.target.value as 'exact' | 'contains' }))
                    }
                    className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                  >
                    <option value="contains">Contains</option>
                    <option value="exact">Exact</option>
                  </select>
                </label>
                <label className="flex flex-col gap-0.5 text-xs text-zinc-600">
                  Match value *
                  <input
                    required
                    value={form.match_value}
                    onChange={(e) => setForm((p) => ({ ...p, match_value: e.target.value }))}
                    className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                    placeholder="swiggy"
                  />
                </label>
                <label className="flex flex-col gap-0.5 text-xs text-zinc-600">
                  Canonical name *
                  <input
                    required
                    value={form.canonical_merchant}
                    onChange={(e) => setForm((p) => ({ ...p, canonical_merchant: e.target.value }))}
                    className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                    placeholder="Swiggy"
                  />
                </label>
                <label className="flex flex-col gap-0.5 text-xs text-zinc-600">
                  Type
                  <input
                    value={form.merchant_type}
                    onChange={(e) => setForm((p) => ({ ...p, merchant_type: e.target.value }))}
                    className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                    placeholder="Optional"
                  />
                </label>
                <label className="flex flex-col gap-0.5 text-xs text-zinc-600">
                  Category *
                  <select
                    required
                    value={form.category}
                    onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
                    className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                  >
                    <option value="">—</option>
                    {MANUAL_TX_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="submit"
                  disabled={busy}
                  className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {editingId !== null ? 'Save' : 'Create'}
                </button>
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="rounded-md border border-zinc-200 px-3 py-1.5 text-xs text-zinc-700 hover:bg-zinc-50"
                >
                  Cancel
                </button>
              </div>
              {formError ? <p className="text-xs text-red-600">{formError}</p> : null}
              {lastApplied !== null ? (
                <p className="text-xs text-emerald-700">
                  Applied to {lastApplied.ledger} ledger + {lastApplied.statement} import row(s).
                </p>
              ) : null}
            </form>
          </Panel>
        ) : null}

        {review !== null ? (
          <Panel padding={false}>
            <div className="border-b border-zinc-100 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-medium text-violet-900">AI suggestions</span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={confirmSelected}
                    disabled={confirmMut.isPending || review.every((r) => !r.checked)}
                    className="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
                  >
                    {confirmMut.isPending ? 'Saving…' : 'Confirm selected'}
                  </button>
                  <button
                    type="button"
                    onClick={() => setReview(null)}
                    className="rounded-md border border-zinc-200 px-2.5 py-1 text-xs text-zinc-700"
                  >
                    Discard
                  </button>
                </div>
              </div>
            </div>
            <div className="max-h-40 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-zinc-50 text-zinc-500">
                  <tr>
                    <th className="w-8 px-2 py-1.5" />
                    <th className="px-2 py-1.5">Raw</th>
                    <th className="px-2 py-1.5">Canonical</th>
                    <th className="px-2 py-1.5">Category</th>
                    <th className="px-2 py-1.5">Conf.</th>
                  </tr>
                </thead>
                <tbody>
                  {review.map((r, i) => (
                    <tr key={r.raw_merchant} className="border-t border-zinc-50">
                      <td className="px-2 py-1">
                        <input
                          type="checkbox"
                          checked={r.checked}
                          onChange={() => toggleReviewChecked(i)}
                        />
                      </td>
                      <td className="max-w-[8rem] truncate px-2 py-1 text-zinc-700">{r.raw_merchant}</td>
                      <td className="px-2 py-1">
                        <input
                          value={r.canonical_merchant}
                          onChange={(e) => updateReviewField(i, 'canonical_merchant', e.target.value)}
                          className="w-full min-w-[6rem] rounded border border-zinc-200 px-1.5 py-0.5 text-xs"
                        />
                      </td>
                      <td className="px-2 py-1">
                        <select
                          value={r.category}
                          onChange={(e) => updateReviewField(i, 'category', e.target.value)}
                          className="rounded border border-zinc-200 px-1.5 py-0.5 text-xs"
                        >
                          {MANUAL_TX_CATEGORIES.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-2 py-1 tabular-nums text-zinc-500">
                        {Math.round(r.confidence * 100)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        ) : null}

        {aiError ? <p className="text-xs text-red-600">{aiError}</p> : null}
      </div>

      <Panel variant="table" padding={false} className="min-h-0 flex-1 overflow-hidden">
        <div className="h-full overflow-auto">
          {activeTab === 'rules' ? (
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="sticky top-0 z-10 border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-3 py-2.5">Match</th>
                  <th className="px-3 py-2.5">Canonical</th>
                  <th className="px-3 py-2.5">Category</th>
                  <th className="px-3 py-2.5">Source</th>
                  <th className="px-3 py-2.5 text-right"> </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {filteredRules.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-10 text-center text-sm text-zinc-500">
                      {rules.length === 0 ? 'No rules yet — click Add rule.' : 'No matches.'}
                    </td>
                  </tr>
                ) : (
                  filteredRules.map((r) => (
                    <tr key={r.id} className="hover:bg-zinc-50/80">
                      <td className="px-3 py-2 text-xs text-zinc-700">
                        <span className="rounded bg-zinc-100 px-1 py-0.5 text-[10px] uppercase text-zinc-500">
                          {r.match_type}
                        </span>{' '}
                        {r.match_value}
                      </td>
                      <td className="px-3 py-2 font-medium text-zinc-900">{r.canonical_merchant}</td>
                      <td className="px-3 py-2 text-xs text-zinc-700">{r.category}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                            r.source === 'user'
                              ? 'bg-emerald-100 text-emerald-800'
                              : r.source === 'llm'
                                ? 'bg-violet-100 text-violet-800'
                                : 'bg-zinc-100 text-zinc-600'
                          }`}
                        >
                          {r.source}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right text-xs whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => startEdit(r)}
                          className="mr-2 font-medium text-emerald-700 hover:underline"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (confirm(`Delete rule for "${r.match_value}"?`)) {
                              deleteMut.mutate(r.id)
                            }
                          }}
                          className="font-medium text-red-600 hover:underline"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          ) : (
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="sticky top-0 z-10 border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="w-8 px-3 py-2.5" />
                  <th className="px-3 py-2.5">Merchant</th>
                  <th className="px-3 py-2.5">Source</th>
                  <th className="px-3 py-2.5 text-right">Freq</th>
                  <th className="px-3 py-2.5 text-right">Total</th>
                  <th className="px-3 py-2.5 text-right"> </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {filteredReview.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-sm text-zinc-500">
                      {uncategorized.length === 0
                        ? 'All merchants categorized.'
                        : 'No matches.'}
                    </td>
                  </tr>
                ) : (
                  filteredReview.map((g) => (
                    <tr key={g.merchant} className="hover:bg-zinc-50/80">
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selectedMerchants.has(g.merchant)}
                          onChange={() => toggleSelected(g.merchant)}
                        />
                      </td>
                      <td className="max-w-[16rem] truncate px-3 py-2 font-medium text-zinc-900">
                        {g.merchant}
                      </td>
                      <td className="px-3 py-2 text-[10px] text-zinc-600">
                        {(g.sources ?? ['ledger']).map((s) => (
                          <span key={s} className="mr-1 rounded bg-zinc-100 px-1 py-0.5">
                            {s === 'statement_import' ? 'CC' : s}
                          </span>
                        ))}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-zinc-700">{g.frequency}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-zinc-700">
                        {formatPaise(g.total_paise)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => prefillFromUncategorized(g.merchant)}
                          className="text-xs font-medium text-emerald-700 hover:underline"
                        >
                          Rule
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>
      </Panel>
    </div>
  )
}
