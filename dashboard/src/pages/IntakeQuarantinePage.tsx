import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Inbox, RefreshCw, XCircle } from 'lucide-react'
import { useState } from 'react'

import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { MANUAL_TX_CATEGORIES } from '@/constants/transactionForm'
import {
  approveIntakeCandidate,
  fetchAccounts,
  fetchIntakeCandidates,
  rejectIntakeCandidate,
} from '@/lib/api'
import { formatPaise } from '@/lib/format'
import type { IntakeCandidate } from '@/types/api'

function confidenceLabel(confidence: number): string {
  return `${Math.round(confidence * 100)}%`
}

function DirectionBadge({ direction }: { direction: IntakeCandidate['direction'] }) {
  const isInflow = direction === 'in'
  return (
    <span
      className={[
        'rounded px-1.5 py-0.5 text-xs font-semibold uppercase',
        isInflow ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700',
      ].join(' ')}
    >
      {isInflow ? 'In' : 'Out'}
    </span>
  )
}

function CandidateReviewModal({
  candidate,
  accountNames,
  onClose,
  onApprove,
  isPending,
  error,
}: {
  candidate: IntakeCandidate
  accountNames: Array<{ id: number; name: string }>
  onClose: () => void
  onApprove: (body: {
    account_id?: number | null
    amount_paise?: number | null
    category?: string | null
    as_transfer?: boolean
    to_account_id?: number | null
  }) => void
  isPending: boolean
  error: string | null
}) {
  const [accountId, setAccountId] = useState('')
  const [category, setCategory] = useState(candidate.suggested_category ?? '')
  const [asTransfer, setAsTransfer] = useState(false)
  const [toAccountId, setToAccountId] = useState('')
  const [openingBalanceAmount, setOpeningBalanceAmount] = useState('')
  const isOpeningBalance = candidate.quarantine_reason === 'needs_opening_balance'
  const effectiveAccountId = accountId || String(candidate.suggested_account_id ?? '')
  const requiresAccount = candidate.suggested_account_id == null
  const amountPaise = Math.round(Number(openingBalanceAmount) * 100)
  const valid = isOpeningBalance
    ? Boolean(effectiveAccountId) && Number.isFinite(amountPaise) && amountPaise > 0
    : Boolean(effectiveAccountId) && (!asTransfer || Boolean(toAccountId))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white shadow-2xl">
        <div className="border-b border-zinc-100 px-6 py-4">
          <h2 className="text-base font-semibold text-zinc-900">Approve ledger entry</h2>
          <p className="mt-1 text-sm text-zinc-500">
            {candidate.payee ?? candidate.narration ?? 'Unnamed transaction'} ·{' '}
            {formatPaise(candidate.amount_paise)}
          </p>
        </div>

        <div className="space-y-4 px-6 py-5">
          <label className="flex flex-col gap-1 text-xs font-medium text-zinc-600">
            {requiresAccount ? 'Account' : 'Account override'}
            <select
              value={accountId}
              onChange={(event) => setAccountId(event.target.value)}
              className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              <option value="">
                {requiresAccount ? 'Select account…' : 'Use suggested account'}
              </option>
              {accountNames.map((account) => (
                <option key={account.id} value={String(account.id)}>
                  {account.name}
                </option>
              ))}
            </select>
            {requiresAccount ? (
              <span className="font-normal text-amber-700">
                An account is required because no suggestion was available.
              </span>
            ) : null}
          </label>

          {isOpeningBalance ? (
            <label className="flex flex-col gap-1 text-xs font-medium text-zinc-600">
              Opening balance amount (₹)
              <input
                type="number"
                min="0.01"
                step="0.01"
                inputMode="decimal"
                value={openingBalanceAmount}
                onChange={(event) => setOpeningBalanceAmount(event.target.value)}
                placeholder="0.00"
                required
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
              <span className="font-normal text-amber-700">
                This balance will be posted against Opening Balance Equity.
              </span>
            </label>
          ) : (
            <>
              <label className="flex flex-col gap-1 text-xs font-medium text-zinc-600">
                Category <span className="font-normal text-zinc-400">(optional)</span>
                <select
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                  className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="">No category</option>
                  {MANUAL_TX_CATEGORIES.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-2 text-sm text-zinc-700">
                <input
                  type="checkbox"
                  checked={asTransfer}
                  onChange={(event) => setAsTransfer(event.target.checked)}
                  className="size-4 rounded border-zinc-300 accent-emerald-600"
                />
                Approve as transfer
              </label>

              {asTransfer ? (
            <label className="flex flex-col gap-1 text-xs font-medium text-zinc-600">
              To account
              <select
                value={toAccountId}
                onChange={(event) => setToAccountId(event.target.value)}
                className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              >
                <option value="">Select destination account…</option>
                {accountNames
                  .filter((account) => String(account.id) !== effectiveAccountId)
                  .map((account) => (
                    <option key={account.id} value={String(account.id)}>
                      {account.name}
                    </option>
                  ))}
              </select>
            </label>
              ) : null}
            </>
          )}

          {error ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p> : null}
        </div>

        <div className="flex justify-end gap-3 border-t border-zinc-100 px-6 py-4">
          <button
            onClick={onClose}
            disabled={isPending}
            className="rounded-lg border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() =>
              onApprove({
                account_id: accountId ? Number(accountId) : null,
                amount_paise: isOpeningBalance ? amountPaise : null,
                category: category || null,
                as_transfer: asTransfer,
                to_account_id: toAccountId ? Number(toAccountId) : null,
              })
            }
            disabled={!valid || isPending}
            className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {isPending ? <RefreshCw className="size-3.5 animate-spin" /> : <CheckCircle2 className="size-3.5" />}
            {isPending ? 'Approving…' : 'Approve'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function IntakeQuarantinePage() {
  const queryClient = useQueryClient()
  const [reviewing, setReviewing] = useState<IntakeCandidate | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [reasonFilter, setReasonFilter] = useState<
    'all' | 'legacy_migration' | 'needs_opening_balance' | 'other'
  >('all')

  const candidatesQ = useQuery({
    queryKey: ['intake-candidates', 'pending'],
    queryFn: () => fetchIntakeCandidates('pending'),
  })
  const accountsQ = useQuery({
    queryKey: ['accounts'],
    queryFn: () => fetchAccounts(true),
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['intake-candidates'] })
    void queryClient.invalidateQueries({ queryKey: ['transactions'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard-alerts'] })
    void queryClient.invalidateQueries({ queryKey: ['budget-vs'] })
  }

  const approveMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof approveIntakeCandidate>[1] }) =>
      approveIntakeCandidate(id, body),
    onSuccess: () => {
      setReviewing(null)
      setActionError(null)
      invalidate()
    },
    onError: (error: Error) => setActionError(error.message),
  })
  const rejectMutation = useMutation({
    mutationFn: rejectIntakeCandidate,
    onSuccess: invalidate,
  })

  const candidates = candidatesQ.data ?? []
  const accounts = accountsQ.data ?? []
  const filteredCandidates = candidates.filter((candidate) => {
    if (reasonFilter === 'all') return true
    if (reasonFilter === 'other') {
      return (
        candidate.quarantine_reason !== 'legacy_migration' &&
        candidate.quarantine_reason !== 'needs_opening_balance'
      )
    }
    return candidate.quarantine_reason === reasonFilter
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        eyebrow="Ledger intake"
        title="Quarantine desk"
        description="Review entries that need a decision before they are posted to the double-entry ledger."
        actions={
          <button
            onClick={() => void candidatesQ.refetch()}
            disabled={candidatesQ.isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 disabled:opacity-50"
          >
            <RefreshCw className={['size-3.5', candidatesQ.isFetching ? 'animate-spin' : ''].join(' ')} />
            Refresh
          </button>
        }
      />

      {candidatesQ.isPending ? (
        <PageLoading />
      ) : candidatesQ.isError ? (
        <PageError
          title="Failed to load quarantine"
          message="Could not fetch pending intake candidates. Check that the API is running."
        />
      ) : candidates.length === 0 ? (
        <Panel>
          <div className="flex flex-col items-center gap-2 py-10 text-center">
            <Inbox className="size-8 text-emerald-600" />
            <p className="text-sm font-medium text-zinc-700">Nothing is waiting for review.</p>
            <p className="text-sm text-zinc-400">New uncertain imports will appear here.</p>
          </div>
        </Panel>
      ) : (
        <Panel className="overflow-hidden p-0">
          <div className="flex flex-wrap gap-2 border-b border-zinc-100 px-4 py-3">
            {(
              [
                ['all', 'All'],
                ['legacy_migration', 'Legacy migration'],
                ['needs_opening_balance', 'Opening balances'],
                ['other', 'Other'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setReasonFilter(value)}
                className={[
                  'rounded-full px-3 py-1 text-xs font-medium transition',
                  reasonFilter === value
                    ? 'bg-emerald-100 text-emerald-900'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          </div>
          {filteredCandidates.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-zinc-500">
              No pending entries match this filter.
            </p>
          ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Transaction</th>
                  <th className="px-4 py-3 font-medium">Direction</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Quarantine reason</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                  <th className="px-4 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {filteredCandidates.map((candidate) => (
                  <tr key={candidate.id} className="align-top">
                    <td className="px-4 py-4">
                      <p className="font-medium text-zinc-800">{candidate.payee ?? 'Unknown payee'}</p>
                      <p className="mt-0.5 text-xs text-zinc-500">
                        {candidate.tx_date} · {formatPaise(candidate.amount_paise)}
                      </p>
                      {candidate.narration ? (
                        <p className="mt-1 max-w-xs text-xs text-zinc-400">{candidate.narration}</p>
                      ) : null}
                    </td>
                    <td className="px-4 py-4"><DirectionBadge direction={candidate.direction} /></td>
                    <td className="px-4 py-4 text-zinc-600">{candidate.source}</td>
                    <td className="max-w-xs px-4 py-4 text-zinc-600">
                      {candidate.quarantine_reason ?? 'Needs review'}
                    </td>
                    <td className="px-4 py-4 text-zinc-600">{confidenceLabel(candidate.confidence)}</td>
                    <td className="px-4 py-4">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => { setActionError(null); setReviewing(candidate) }}
                          className="flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-700"
                        >
                          <CheckCircle2 className="size-3.5" />
                          Approve
                        </button>
                        <button
                          onClick={() => rejectMutation.mutate(candidate.id)}
                          disabled={rejectMutation.isPending}
                          className="flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                        >
                          <XCircle className="size-3.5" />
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
          {rejectMutation.isError ? (
            <p className="border-t border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
              {(rejectMutation.error as Error).message}
            </p>
          ) : null}
        </Panel>
      )}

      {reviewing ? (
        <CandidateReviewModal
          candidate={reviewing}
          accountNames={accounts}
          onClose={() => { setReviewing(null); setActionError(null) }}
          onApprove={(body) => approveMutation.mutate({ id: reviewing.id, body })}
          isPending={approveMutation.isPending}
          error={actionError}
        />
      ) : null}
    </div>
  )
}
