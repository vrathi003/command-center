import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
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
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
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
  const [lastApplied, setLastApplied] = useState<number | null>(null)
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
  }

  const createMut = useMutation({
    mutationFn: postMerchantRule,
    onSuccess: (r) => {
      invalidateAll()
      setForm(BLANK)
      setFormError(null)
      setLastApplied(r.retroactively_applied ?? 0)
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
      setLastApplied(r.retroactively_applied ?? 0)
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
      setLastApplied(r.total_retroactively_applied)
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
  }

  const cancelEdit = () => {
    setEditingId(null)
    setForm(BLANK)
    setFormError(null)
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

  if (qRules.isLoading || qUncategorized.isLoading) return <PageLoading />
  if (qRules.isError) return <PageError title="Error" message="Could not load merchant rules." />

  const rules = qRules.data ?? []
  const uncategorized = qUncategorized.data ?? []
  const busy = createMut.isPending || updateMut.isPending

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Cash flow"
        title="Merchants"
        description="Map raw merchant strings to a canonical name, type, and category — used automatically on import, email sync, and Discord logging."
        actions={
          <Link
            to="/transactions"
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50"
          >
            Back to transactions
          </Link>
        }
      />

      <section>
        <SectionTitle>{editingId !== null ? 'Edit rule' : 'New rule'}</SectionTitle>
        <Panel>
          <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Match type</span>
              <select
                value={form.match_type}
                onChange={(e) =>
                  setForm((p) => ({ ...p, match_type: e.target.value as 'exact' | 'contains' }))
                }
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="contains">Contains</option>
                <option value="exact">Exact</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Match value *</span>
              <input
                required
                value={form.match_value}
                onChange={(e) => setForm((p) => ({ ...p, match_value: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="e.g. swiggy"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Canonical merchant *</span>
              <input
                required
                value={form.canonical_merchant}
                onChange={(e) => setForm((p) => ({ ...p, canonical_merchant: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="e.g. Swiggy"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Merchant type</span>
              <input
                value={form.merchant_type}
                onChange={(e) => setForm((p) => ({ ...p, merchant_type: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="e.g. Food Delivery Platform"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Category *</span>
              <select
                required
                value={form.category}
                onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">—</option>
                {MANUAL_TX_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex flex-wrap items-end gap-2 sm:col-span-2 lg:col-span-3">
              <button
                type="submit"
                disabled={busy}
                className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
              >
                {editingId !== null ? 'Save changes' : 'Create rule'}
              </button>
              {editingId !== null ? (
                <button
                  type="button"
                  onClick={cancelEdit}
                  className="rounded-xl border border-zinc-200 px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm hover:bg-zinc-50"
                >
                  Cancel
                </button>
              ) : null}
            </div>
            {formError ? (
              <p className="text-sm text-red-600 sm:col-span-2 lg:col-span-3">{formError}</p>
            ) : null}
            {lastApplied !== null ? (
              <p className="text-sm text-emerald-700 sm:col-span-2 lg:col-span-3">
                Applied retroactively to {lastApplied} existing transaction
                {lastApplied !== 1 ? 's' : ''}.
              </p>
            ) : null}
          </form>
        </Panel>
      </section>

      <section>
        <SectionTitle>
          {rules.length} rule{rules.length !== 1 ? 's' : ''}
        </SectionTitle>
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-zinc-600">
                  <th className="py-2 pr-3 font-medium">Match</th>
                  <th className="py-2 pr-3 font-medium">Canonical merchant</th>
                  <th className="py-2 pr-3 font-medium">Type</th>
                  <th className="py-2 pr-3 font-medium">Category</th>
                  <th className="py-2 pr-3 font-medium">Source</th>
                  <th className="py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((r) => (
                  <tr key={r.id} className="border-b border-zinc-100">
                    <td className="py-2 pr-3 text-zinc-700">
                      <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs uppercase text-zinc-500">
                        {r.match_type}
                      </span>{' '}
                      {r.match_value}
                    </td>
                    <td className="py-2 pr-3 font-medium text-zinc-900">{r.canonical_merchant}</td>
                    <td className="py-2 pr-3 text-zinc-600">{r.merchant_type ?? '—'}</td>
                    <td className="py-2 pr-3 text-zinc-700">{r.category}</td>
                    <td className="py-2 pr-3">
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-medium ${
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
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        onClick={() => startEdit(r)}
                        className="mr-2 text-emerald-700 hover:underline"
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
                        className="text-red-600 hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rules.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-600">No rules yet.</p>
            ) : null}
          </div>
        </Panel>
      </section>

      <section>
        <SectionTitle>
          Uncategorized merchants ({uncategorized.length})
        </SectionTitle>
        <Panel>
          {aiError ? <p className="mb-3 text-sm text-red-600">{aiError}</p> : null}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={runClassifyWithAi}
              disabled={selectedMerchants.size === 0 || suggestMut.isPending}
              className="rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-violet-700 disabled:opacity-50"
            >
              {suggestMut.isPending
                ? 'Classifying…'
                : `Classify ${selectedMerchants.size || ''} with AI`.trim()}
            </button>
            <span className="text-xs text-zinc-500">
              Select merchants below, then review AI suggestions before anything is saved.
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-zinc-600">
                  <th className="py-2 pr-3 font-medium"> </th>
                  <th className="py-2 pr-3 font-medium">Merchant</th>
                  <th className="py-2 pr-3 font-medium">Frequency</th>
                  <th className="py-2 pr-3 font-medium">Total</th>
                  <th className="py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {uncategorized.map((g) => (
                  <tr key={g.merchant} className="border-b border-zinc-100">
                    <td className="py-2 pr-3">
                      <input
                        type="checkbox"
                        checked={selectedMerchants.has(g.merchant)}
                        onChange={() => toggleSelected(g.merchant)}
                      />
                    </td>
                    <td className="py-2 pr-3 font-medium text-zinc-900">{g.merchant}</td>
                    <td className="py-2 pr-3 text-zinc-700">{g.frequency}</td>
                    <td className="py-2 pr-3 text-zinc-700">{formatPaise(g.total_paise)}</td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        onClick={() => prefillFromUncategorized(g.merchant)}
                        className="text-emerald-700 hover:underline"
                      >
                        Create rule
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {uncategorized.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-600">Nothing uncategorized right now.</p>
            ) : null}
          </div>
        </Panel>
      </section>

      {review !== null ? (
        <section>
          <SectionTitle>Review AI suggestions</SectionTitle>
          <Panel>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-zinc-600">
                    <th className="py-2 pr-3 font-medium"> </th>
                    <th className="py-2 pr-3 font-medium">Raw merchant</th>
                    <th className="py-2 pr-3 font-medium">Canonical merchant</th>
                    <th className="py-2 pr-3 font-medium">Category</th>
                    <th className="py-2 pr-3 font-medium">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {review.map((r, i) => (
                    <tr key={r.raw_merchant} className="border-b border-zinc-100">
                      <td className="py-2 pr-3">
                        <input
                          type="checkbox"
                          checked={r.checked}
                          onChange={() => toggleReviewChecked(i)}
                        />
                      </td>
                      <td className="py-2 pr-3 text-zinc-700">{r.raw_merchant}</td>
                      <td className="py-2 pr-3">
                        <input
                          value={r.canonical_merchant}
                          onChange={(e) =>
                            updateReviewField(i, 'canonical_merchant', e.target.value)
                          }
                          className="rounded-lg border border-zinc-200 px-2 py-1 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                        />
                      </td>
                      <td className="py-2 pr-3">
                        <select
                          value={r.category}
                          onChange={(e) => updateReviewField(i, 'category', e.target.value)}
                          className="rounded-lg border border-zinc-200 px-2 py-1 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                        >
                          {MANUAL_TX_CATEGORIES.map((c) => (
                            <option key={c} value={c}>
                              {c}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-2 pr-3 text-zinc-700">
                        {Math.round(r.confidence * 100)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={confirmSelected}
                disabled={confirmMut.isPending || review.every((r) => !r.checked)}
                className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
              >
                {confirmMut.isPending ? 'Saving…' : 'Confirm selected'}
              </button>
              <button
                type="button"
                onClick={() => setReview(null)}
                className="rounded-xl border border-zinc-200 px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm hover:bg-zinc-50"
              >
                Discard
              </button>
            </div>
          </Panel>
        </section>
      ) : null}
    </div>
  )
}
