import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { MANUAL_TX_CATEGORIES, PAYMENT_MODE_OPTIONS } from '@/constants/transactionForm'
import {
  deleteTransactionTemplate,
  fetchAccounts,
  fetchTransactionTemplates,
  postTransactionTemplate,
  putTransactionTemplate,
} from '@/lib/api'
import { formatPaise } from '@/lib/format'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import type { TransactionTemplateOut } from '@/types/api'

const BLANK = {
  name: '',
  amountRu: '' as string,
  merchant: '',
  category: '',
  account_id: '' as string,
  payment_mode: '',
  transaction_type: 'debit' as 'debit' | 'credit' | 'transfer',
  notes: '',
  tags: '',
}

function toBody(f: typeof BLANK) {
  const ru = f.amountRu.trim()
  const amountPaise =
    ru === '' ? null : Math.round(parseFloat(ru.replace(/,/g, '')) * 100)
  if (amountPaise !== null && (Number.isNaN(amountPaise) || amountPaise < 0)) {
    throw new Error('Invalid amount')
  }
  return {
    name: f.name.trim(),
    amount: amountPaise,
    merchant: f.merchant.trim() || null,
    category: f.category.trim() || null,
    account_id: f.account_id === '' ? null : Number(f.account_id),
    payment_mode: f.payment_mode.trim() || null,
    transaction_type: f.transaction_type,
    notes: f.notes.trim() || null,
    tags: f.tags.trim() || null,
  }
}

export function TransactionTemplatesPage() {
  const qc = useQueryClient()
  const [form, setForm] = useState(BLANK)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const qAccounts = useQuery({
    queryKey: ['accounts', true],
    queryFn: () => fetchAccounts(true),
  })
  const q = useQuery({
    queryKey: ['transaction-templates'],
    queryFn: fetchTransactionTemplates,
  })

  const createMut = useMutation({
    mutationFn: postTransactionTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transaction-templates'] })
      setForm(BLANK)
      setFormError(null)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: number
      body: Parameters<typeof putTransactionTemplate>[1]
    }) => putTransactionTemplate(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['transaction-templates'] })
      setEditingId(null)
      setForm(BLANK)
      setFormError(null)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: deleteTransactionTemplate,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['transaction-templates'] }),
  })

  const accountNameById = useMemo(() => {
    const m = new Map<number, string>()
    for (const a of qAccounts.data ?? []) {
      m.set(a.id, a.name)
    }
    return m
  }, [qAccounts.data])

  const startEdit = (t: TransactionTemplateOut) => {
    setEditingId(t.id)
    setForm({
      name: t.name,
      amountRu:
        t.amount !== null ? (t.amount / 100).toFixed(2).replace(/\.?0+$/, '') : '',
      merchant: t.merchant ?? '',
      category: t.category ?? '',
      account_id: t.account_id != null ? String(t.account_id) : '',
      payment_mode: t.payment_mode ?? '',
      transaction_type: t.transaction_type,
      notes: t.notes ?? '',
      tags: t.tags ?? '',
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
    try {
      const body = toBody(form)
      if (!body.name) {
        setFormError('Name is required.')
        return
      }
      if (editingId !== null) {
        updateMut.mutate({ id: editingId, body })
      } else {
        createMut.mutate(body)
      }
    } catch {
      setFormError('Check amount and fields.')
    }
  }

  if (q.isLoading || qAccounts.isLoading) return <PageLoading />
  if (q.isError) return <PageError title="Error" message="Could not load templates." />

  const rows = q.data ?? []
  const busy = createMut.isPending || updateMut.isPending

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Cash flow"
        title="Transaction templates"
        description="Quick-add presets for recurring entries (amount optional — fill at use time)."
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
        <SectionTitle>{editingId !== null ? 'Edit template' : 'New template'}</SectionTitle>
        <Panel>
          <form onSubmit={onSubmit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Name *</span>
              <input
                required
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="e.g. Monthly rent"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Amount (₹)</span>
              <input
                value={form.amountRu}
                onChange={(e) => setForm((p) => ({ ...p, amountRu: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="Leave blank to enter at log time"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Type</span>
              <select
                value={form.transaction_type}
                onChange={(e) =>
                  setForm((p) => ({
                    ...p,
                    transaction_type: e.target.value as typeof form.transaction_type,
                  }))
                }
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="debit">Debit</option>
                <option value="credit">Credit</option>
                <option value="transfer">Transfer</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Category</span>
              <select
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
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Merchant</span>
              <input
                value={form.merchant}
                onChange={(e) => setForm((p) => ({ ...p, merchant: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Account</span>
              <select
                value={form.account_id}
                onChange={(e) => setForm((p) => ({ ...p, account_id: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">—</option>
                {(qAccounts.data ?? []).map((a) => (
                  <option key={a.id} value={String(a.id)}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700">
              <span className="font-medium">Payment mode</span>
              <select
                value={form.payment_mode}
                onChange={(e) => setForm((p) => ({ ...p, payment_mode: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                <option value="">—</option>
                {PAYMENT_MODE_OPTIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700 sm:col-span-2">
              <span className="font-medium">Notes</span>
              <input
                value={form.notes}
                onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-zinc-700 sm:col-span-2">
              <span className="font-medium">Tags</span>
              <input
                value={form.tags}
                onChange={(e) => setForm((p) => ({ ...p, tags: e.target.value }))}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                placeholder="comma-separated"
              />
            </label>
            <div className="flex flex-wrap items-end gap-2 sm:col-span-2 lg:col-span-3">
              <button
                type="submit"
                disabled={busy}
                className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
              >
                {editingId !== null ? 'Save changes' : 'Create template'}
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
          </form>
        </Panel>
      </section>

      <section>
        <SectionTitle>{rows.length} template{rows.length !== 1 ? 's' : ''}</SectionTitle>
        <Panel>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-zinc-600">
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Amount</th>
                  <th className="py-2 pr-3 font-medium">Type</th>
                  <th className="py-2 pr-3 font-medium">Category</th>
                  <th className="py-2 pr-3 font-medium">Account</th>
                  <th className="py-2 pr-3 font-medium">Payment</th>
                  <th className="py-2 pr-3 font-medium">Tags</th>
                  <th className="py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((t) => (
                  <tr key={t.id} className="border-b border-zinc-100">
                    <td className="py-2 pr-3 font-medium text-zinc-900">{t.name}</td>
                    <td className="py-2 pr-3 text-zinc-700">
                      {t.amount !== null ? formatPaise(t.amount) : '—'}
                    </td>
                    <td className="py-2 pr-3 text-zinc-700">{t.transaction_type}</td>
                    <td className="py-2 pr-3 text-zinc-700">{t.category ?? '—'}</td>
                    <td className="py-2 pr-3 text-zinc-700">
                      {t.account_id != null ? accountNameById.get(t.account_id) ?? '—' : '—'}
                    </td>
                    <td className="py-2 pr-3 text-zinc-700">{t.payment_mode ?? '—'}</td>
                    <td className="py-2 pr-3 text-zinc-600">{t.tags ?? '—'}</td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        onClick={() => startEdit(t)}
                        className="mr-2 text-emerald-700 hover:underline"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (confirm(`Delete template “${t.name}”?`)) {
                            deleteMut.mutate(t.id)
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
            {rows.length === 0 ? (
              <p className="mt-2 text-sm text-zinc-600">No templates yet.</p>
            ) : null}
          </div>
        </Panel>
      </section>
    </div>
  )
}
