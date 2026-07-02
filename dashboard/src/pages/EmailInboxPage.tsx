import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle, RefreshCw, Trash2, XCircle } from 'lucide-react'
import { useState } from 'react'

import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { MANUAL_TX_CATEGORIES, PAYMENT_MODE_OPTIONS } from '@/constants/transactionForm'
import {
  approveEmailTransaction,
  clearRejectedEmails,
  fetchEmailInbox,
  fetchEmailInboxStats,
  rejectEmailTransaction,
  syncGmailNow,
  updateStagedEmail,
} from '@/lib/api'
import { formatPaise } from '@/lib/format'
import type { StagedEmailTransaction } from '@/types/api'

type Tab = 'pending' | 'approved' | 'rejected'

function formatEmailDate(d: string): string {
  try {
    return new Date(d).toLocaleString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return d
  }
}

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n <= 0) return null
  return Math.round(n * 100)
}

function paiseToRupees(p: number): string {
  return (p / 100).toFixed(2)
}

// ── Inline edit form ─────────────────────────────────────────────────────────

interface EditState {
  parsed_date: string
  parsed_amount: string
  parsed_merchant: string
  parsed_category: string
  parsed_payment_mode: string
  parsed_transaction_type: 'debit' | 'credit'
}

function itemToEditState(item: StagedEmailTransaction): EditState {
  return {
    parsed_date: item.parsed_date ?? '',
    parsed_amount: item.parsed_amount_paise ? paiseToRupees(item.parsed_amount_paise) : '',
    parsed_merchant: item.parsed_merchant ?? '',
    parsed_category: item.parsed_category ?? 'Other',
    parsed_payment_mode: item.parsed_payment_mode ?? 'Other',
    parsed_transaction_type: (item.parsed_transaction_type as 'debit' | 'credit') ?? 'debit',
  }
}

// ── Item card ────────────────────────────────────────────────────────────────

interface ItemCardProps {
  item: StagedEmailTransaction
  onApprove: (item: StagedEmailTransaction, overrides: EditState) => void
  onReject: (item: StagedEmailTransaction) => void
  approving: boolean
  rejecting: boolean
}

function PendingCard({ item, onApprove, onReject, approving, rejecting }: ItemCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<EditState>(() => itemToEditState(item))

  function field(key: keyof EditState, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span>{item.email_from ?? '—'}</span>
            <span>·</span>
            <span>{formatEmailDate(item.email_date)}</span>
          </div>
          {item.email_subject && (
            <p className="mt-0.5 truncate text-sm font-medium text-zinc-700">
              {item.email_subject}
            </p>
          )}
        </div>
        {item.parsed_transaction_type && (
          <span
            className={[
              'shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold uppercase',
              item.parsed_transaction_type === 'credit'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-red-50 text-red-700',
            ].join(' ')}
          >
            {item.parsed_transaction_type === 'credit' ? 'CR' : 'DR'}
          </span>
        )}
      </div>

      {/* Parsed summary */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span className="text-zinc-500">
          Date:{' '}
          <span className="font-medium text-zinc-800">{item.parsed_date ?? '—'}</span>
        </span>
        <span className="text-zinc-500">
          Amount:{' '}
          <span className="font-medium text-zinc-800">
            {item.parsed_amount_paise != null ? formatPaise(item.parsed_amount_paise) : '—'}
          </span>
        </span>
        <span className="text-zinc-500">
          Merchant:{' '}
          <span className="font-medium text-zinc-800">{item.parsed_merchant ?? '—'}</span>
        </span>
        <span className="text-zinc-500">
          Category:{' '}
          <span className="font-medium text-zinc-800">{item.parsed_category ?? '—'}</span>
        </span>
      </div>

      {/* Raw snippet toggle */}
      {item.raw_snippet && (
        <button
          onClick={() => setExpanded((p) => !p)}
          className="mt-2 text-xs text-zinc-400 underline-offset-2 hover:text-zinc-600 hover:underline"
        >
          {expanded ? 'Hide snippet' : 'Show snippet'}
        </button>
      )}
      {expanded && item.raw_snippet && (
        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-zinc-50 p-3 text-xs text-zinc-600">
          {item.raw_snippet}
        </pre>
      )}

      {/* Inline edit form */}
      {editing && (
        <div className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-zinc-100 bg-zinc-50 p-4 sm:grid-cols-3">
          <label className="col-span-1 flex flex-col gap-1 text-xs font-medium text-zinc-600">
            Date
            <input
              type="date"
              value={form.parsed_date}
              onChange={(e) => field('parsed_date', e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1 text-sm text-zinc-800"
            />
          </label>
          <label className="col-span-1 flex flex-col gap-1 text-xs font-medium text-zinc-600">
            Amount (₹)
            <input
              type="number"
              min={0}
              step={0.01}
              value={form.parsed_amount}
              onChange={(e) => field('parsed_amount', e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1 text-sm text-zinc-800"
            />
          </label>
          <label className="col-span-1 flex flex-col gap-1 text-xs font-medium text-zinc-600">
            Type
            <select
              value={form.parsed_transaction_type}
              onChange={(e) =>
                field('parsed_transaction_type', e.target.value as 'debit' | 'credit')
              }
              className="rounded border border-zinc-200 bg-white px-2 py-1 text-sm text-zinc-800"
            >
              <option value="debit">Debit</option>
              <option value="credit">Credit</option>
            </select>
          </label>
          <label className="col-span-1 flex flex-col gap-1 text-xs font-medium text-zinc-600 sm:col-span-2">
            Merchant
            <input
              type="text"
              value={form.parsed_merchant}
              onChange={(e) => field('parsed_merchant', e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1 text-sm text-zinc-800"
            />
          </label>
          <label className="col-span-1 flex flex-col gap-1 text-xs font-medium text-zinc-600">
            Category
            <select
              value={form.parsed_category}
              onChange={(e) => field('parsed_category', e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1 text-sm text-zinc-800"
            >
              {MANUAL_TX_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="col-span-2 flex flex-col gap-1 text-xs font-medium text-zinc-600 sm:col-span-3">
            Payment mode
            <select
              value={form.parsed_payment_mode}
              onChange={(e) => field('parsed_payment_mode', e.target.value)}
              className="rounded border border-zinc-200 bg-white px-2 py-1 text-sm text-zinc-800"
            >
              {PAYMENT_MODE_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {/* Action buttons */}
      <div className="mt-4 flex items-center gap-2">
        <button
          onClick={() => onApprove(item, form)}
          disabled={approving || rejecting}
          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          <CheckCircle className="size-3.5" />
          {approving ? 'Approving…' : 'Approve'}
        </button>
        <button
          onClick={() => setEditing((p) => !p)}
          className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          {editing ? 'Done editing' : 'Edit'}
        </button>
        <button
          onClick={() => onReject(item)}
          disabled={approving || rejecting}
          className="flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
        >
          <XCircle className="size-3.5" />
          {rejecting ? 'Rejecting…' : 'Reject'}
        </button>
      </div>
    </div>
  )
}

function ReadOnlyCard({ item }: { item: StagedEmailTransaction }) {
  return (
    <div className="rounded-lg border border-zinc-100 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span>{item.email_from ?? '—'}</span>
            <span>·</span>
            <span>{formatEmailDate(item.email_date)}</span>
          </div>
          {item.email_subject && (
            <p className="mt-0.5 truncate text-sm font-medium text-zinc-600">
              {item.email_subject}
            </p>
          )}
        </div>
        {item.parsed_transaction_type && (
          <span
            className={[
              'shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold uppercase',
              item.parsed_transaction_type === 'credit'
                ? 'bg-emerald-50 text-emerald-700'
                : 'bg-red-50 text-red-700',
            ].join(' ')}
          >
            {item.parsed_transaction_type === 'credit' ? 'CR' : 'DR'}
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span className="text-zinc-400">
          {item.parsed_date ?? '—'} ·{' '}
          {item.parsed_amount_paise != null ? formatPaise(item.parsed_amount_paise) : '—'} ·{' '}
          {item.parsed_merchant ?? '—'} · {item.parsed_category ?? '—'}
        </span>
      </div>
    </div>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export function EmailInboxPage() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('pending')
  const [activeMutations, setActiveMutations] = useState<Record<number, 'approving' | 'rejecting'>>({})

  const statsQ = useQuery({
    queryKey: ['email-inbox-stats'],
    queryFn: fetchEmailInboxStats,
    refetchInterval: 5 * 60 * 1000,
  })

  const listQ = useQuery({
    queryKey: ['email-inbox', tab],
    queryFn: () => fetchEmailInbox(tab),
  })

  function invalidate() {
    qc.invalidateQueries({ queryKey: ['email-inbox'] })
    qc.invalidateQueries({ queryKey: ['email-inbox-stats'] })
  }

  const syncMut = useMutation({
    mutationFn: syncGmailNow,
    onSuccess: invalidate,
  })

  const approveMut = useMutation({
    mutationFn: ({
      id,
      form,
    }: {
      id: number
      form: EditState
    }) => {
      const amount_paise = rupeesToPaise(form.parsed_amount)
      return approveEmailTransaction(id, {
        parsed_date: form.parsed_date || null,
        parsed_amount_paise: amount_paise,
        parsed_merchant: form.parsed_merchant || null,
        parsed_category: form.parsed_category || null,
        parsed_payment_mode: form.parsed_payment_mode || null,
        parsed_transaction_type: form.parsed_transaction_type,
      })
    },
    onMutate: ({ id }) => setActiveMutations((p) => ({ ...p, [id]: 'approving' })),
    onSettled: (_, __, { id }) => {
      setActiveMutations((p) => {
        const n = { ...p }
        delete n[id]
        return n
      })
      invalidate()
    },
  })

  const rejectMut = useMutation({
    mutationFn: ({ id }: { id: number }) => rejectEmailTransaction(id),
    onMutate: ({ id }) => setActiveMutations((p) => ({ ...p, [id]: 'rejecting' })),
    onSettled: (_, __, { id }) => {
      setActiveMutations((p) => {
        const n = { ...p }
        delete n[id]
        return n
      })
      invalidate()
    },
  })

  const clearMut = useMutation({
    mutationFn: clearRejectedEmails,
    onSuccess: invalidate,
  })

  const stats = statsQ.data
  const items = listQ.data ?? []

  const TABS: { key: Tab; label: string; count: number | undefined }[] = [
    { key: 'pending', label: 'Pending', count: stats?.pending },
    { key: 'approved', label: 'Approved', count: stats?.approved },
    { key: 'rejected', label: 'Rejected', count: stats?.rejected },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        eyebrow="Gmail"
        title="Transaction Inbox"
        description="Review transaction emails parsed from your Gmail account. Approve to add to the ledger."
        actions={
          <button
            onClick={() => syncMut.mutate()}
            disabled={syncMut.isPending}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 disabled:opacity-50"
          >
            <RefreshCw className={['size-3.5', syncMut.isPending ? 'animate-spin' : ''].join(' ')} />
            {syncMut.isPending ? 'Syncing…' : 'Sync now'}
          </button>
        }
      />

      {syncMut.isSuccess && (
        <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          Sync complete — {syncMut.data.new_items} new item(s) added.
        </div>
      )}

      {syncMut.isError && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          Sync failed. Make sure Gmail is configured with a valid credentials file.
        </div>
      )}

      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-zinc-200">
        {TABS.map(({ key, label, count }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={[
              'flex items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === key
                ? 'border-emerald-600 text-emerald-700'
                : 'border-transparent text-zinc-500 hover:text-zinc-700',
            ].join(' ')}
          >
            {label}
            {count != null && (
              <span
                className={[
                  'rounded-full px-1.5 py-0.5 text-xs font-semibold',
                  tab === key
                    ? 'bg-emerald-100 text-emerald-700'
                    : 'bg-zinc-100 text-zinc-500',
                  key === 'pending' && count > 0 ? 'bg-orange-100 text-orange-700' : '',
                ].join(' ')}
              >
                {count}
              </span>
            )}
          </button>
        ))}

        {tab === 'rejected' && (stats?.rejected ?? 0) > 0 && (
          <button
            onClick={() => clearMut.mutate()}
            disabled={clearMut.isPending}
            className="ml-auto flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            <Trash2 className="size-3" />
            {clearMut.isPending ? 'Clearing…' : 'Clear all rejected'}
          </button>
        )}
      </div>

      {/* Content */}
      {listQ.isPending ? (
        <PageLoading />
      ) : listQ.isError ? (
        <PageError message="Failed to load email inbox" />
      ) : items.length === 0 ? (
        <Panel>
          <p className="py-8 text-center text-sm text-zinc-400">
            {tab === 'pending'
              ? 'No pending emails. Click "Sync now" to fetch recent emails.'
              : `No ${tab} items.`}
          </p>
        </Panel>
      ) : (
        <div className="flex flex-col gap-3">
          {tab === 'pending'
            ? items.map((item) => (
                <PendingCard
                  key={item.id}
                  item={item}
                  approving={activeMutations[item.id] === 'approving'}
                  rejecting={activeMutations[item.id] === 'rejecting'}
                  onApprove={(it, form) => approveMut.mutate({ id: it.id, form })}
                  onReject={(it) => rejectMut.mutate({ id: it.id })}
                />
              ))
            : items.map((item) => <ReadOnlyCard key={item.id} item={item} />)}
        </div>
      )}
    </div>
  )
}
