import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarSearch, CheckCircle, RefreshCw, Trash2, XCircle } from 'lucide-react'
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
  historicalSyncGmail,
  rejectEmailTransaction,
  syncGmailNow,
  updateStagedEmail,
} from '@/lib/api'
import { formatPaise } from '@/lib/format'
import type { HistoricalSyncResult, StagedEmailTransaction } from '@/types/api'

const MAX_HISTORICAL_DAYS = 90

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

// ── Historical import panel ───────────────────────────────────────────────────

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function daysAgoIso(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}

function daysBetween(a: string, b: string): number {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86_400_000)
}

interface HistoricalImportPanelProps {
  onComplete: () => void
}

function HistoricalImportPanel({ onComplete }: HistoricalImportPanelProps) {
  const [open, setOpen] = useState(false)
  const [fromDate, setFromDate] = useState(daysAgoIso(30))
  const [toDate, setToDate] = useState(todayIso())
  const [confirming, setConfirming] = useState(false)
  const [result, setResult] = useState<HistoricalSyncResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const days = daysBetween(fromDate, toDate)
  const rangeError =
    !fromDate || !toDate
      ? 'Both dates are required.'
      : days < 0
        ? 'From date must be before To date.'
        : days > MAX_HISTORICAL_DAYS
          ? `Range cannot exceed ${MAX_HISTORICAL_DAYS} days (currently ${days} days).`
          : null

  const importMut = useMutation({
    mutationFn: () => historicalSyncGmail(fromDate, toDate),
    onSuccess: (data) => {
      setResult(data)
      setConfirming(false)
      onComplete()
    },
    onError: (err: Error) => {
      setError(err.message)
      setConfirming(false)
    },
  })

  function handleConfirm() {
    setError(null)
    setResult(null)
    importMut.mutate()
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white shadow-sm">
      {/* Collapsible header */}
      <button
        onClick={() => { setOpen((p) => !p); setResult(null); setError(null) }}
        className="flex w-full items-center gap-2 px-5 py-4 text-left"
      >
        <CalendarSearch className="size-4 shrink-0 text-zinc-500" />
        <span className="flex-1 text-sm font-medium text-zinc-700">Historical Import</span>
        <span className="text-xs text-zinc-400">{open ? '▲ collapse' : '▼ expand'}</span>
      </button>

      {open && (
        <div className="border-t border-zinc-100 px-5 pb-5 pt-4">
          <p className="mb-4 text-xs text-zinc-500">
            Pull older emails by date range. Max {MAX_HISTORICAL_DAYS} days per import — run
            multiple times for longer periods. Does not affect the automatic 3-hour sync.
          </p>

          <div className="flex flex-wrap items-end gap-4">
            <label className="flex flex-col gap-1 text-xs font-medium text-zinc-600">
              From
              <input
                type="date"
                value={fromDate}
                max={todayIso()}
                onChange={(e) => { setFromDate(e.target.value); setResult(null) }}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-zinc-600">
              To
              <input
                type="date"
                value={toDate}
                max={todayIso()}
                onChange={(e) => { setToDate(e.target.value); setResult(null) }}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </label>
            {fromDate && toDate && !rangeError && (
              <span className="mb-2 text-xs text-zinc-400">{days} day{days !== 1 ? 's' : ''}</span>
            )}
          </div>

          {rangeError && (
            <p className="mt-2 text-xs text-red-600">{rangeError}</p>
          )}

          <button
            onClick={() => setConfirming(true)}
            disabled={!!rangeError || importMut.isPending}
            className="mt-4 flex items-center gap-2 rounded-lg bg-zinc-800 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:opacity-40"
          >
            <CalendarSearch className="size-3.5" />
            Import emails from this range
          </button>

          {/* Result banner */}
          {result && (
            <div className="mt-4 rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              Done — {result.new_items} new item(s) staged from {result.total_scanned} email(s)
              scanned ({result.from_date} → {result.to_date}).
            </div>
          )}
          {error && (
            <div className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>
      )}

      {/* Confirmation dialog */}
      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
            <h2 className="text-base font-semibold text-zinc-900">Confirm historical import</h2>
            <p className="mt-2 text-sm text-zinc-600">
              This will scan <span className="font-medium">{days} day{days !== 1 ? 's' : ''}</span>{' '}
              of Gmail ({fromDate} → {toDate}) for bank and merchant transaction emails.
            </p>
            <p className="mt-1 text-sm text-zinc-600">
              Found emails will be added to the <span className="font-medium">Pending</span> tab
              for your review. Duplicates (already staged) are skipped automatically.
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                onClick={() => setConfirming(false)}
                className="rounded-lg border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                disabled={importMut.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {importMut.isPending ? (
                  <>
                    <RefreshCw className="size-3.5 animate-spin" />
                    Importing…
                  </>
                ) : (
                  'Yes, import'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
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

      <HistoricalImportPanel onComplete={invalidate} />

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
