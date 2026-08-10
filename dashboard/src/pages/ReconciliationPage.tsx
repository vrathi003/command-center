import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, RefreshCw, Scale, Sparkles, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'

import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import {
  confirmReconMatch,
  createReconAdjustment,
  fetchAccounts,
  fetchLedgerTransactions,
  fetchReconStatements,
  fetchReconWorkspace,
  ignoreReconLine,
  reopenReconStatement,
  softCloseReconStatement,
  suggestReconMatches,
} from '@/lib/api'
import { formatPaise } from '@/lib/format'
import type { ReconStatementLine } from '@/types/api'

function StatusBadge({ status }: { status: 'unmatched' | 'matched' | 'ignored' | 'open' | 'reconciled' }) {
  const styles = {
    unmatched: 'bg-amber-50 text-amber-700',
    matched: 'bg-emerald-50 text-emerald-700',
    ignored: 'bg-zinc-100 text-zinc-600',
    open: 'bg-blue-50 text-blue-700',
    reconciled: 'bg-emerald-50 text-emerald-700',
  }
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${styles[status]}`}>
      {status}
    </span>
  )
}

export function ReconciliationPage() {
  const queryClient = useQueryClient()
  const [accountId, setAccountId] = useState<number | null>(null)
  const [statementId, setStatementId] = useState<number | null>(null)
  const [selectedLineId, setSelectedLineId] = useState<number | null>(null)
  const [suggestions, setSuggestions] = useState<Record<number, Array<{ ledger_transaction_id: number; score: number; reasons: string[] }>>>({})
  const [manualLedgerId, setManualLedgerId] = useState('')
  const [adjusting, setAdjusting] = useState(false)
  const [counterpartAccountId, setCounterpartAccountId] = useState('')
  const [category, setCategory] = useState('Bank charges')

  const accountsQ = useQuery({ queryKey: ['accounts'], queryFn: () => fetchAccounts(true) })
  const statementsQ = useQuery({
    queryKey: ['recon-statements', accountId],
    queryFn: () => fetchReconStatements(accountId!),
    enabled: accountId !== null,
  })

  useEffect(() => {
    if (accountId === null && accountsQ.data?.length) setAccountId(accountsQ.data[0].id)
  }, [accountId, accountsQ.data])

  useEffect(() => {
    const statements = statementsQ.data ?? []
    if (statements.length && !statements.some((statement) => statement.id === statementId)) {
      setStatementId(statements[0].id)
    }
    if (!statements.length) setStatementId(null)
  }, [statementId, statementsQ.data])

  const workspaceQ = useQuery({
    queryKey: ['recon-workspace', statementId],
    queryFn: () => fetchReconWorkspace(statementId!),
    enabled: statementId !== null,
  })
  const workspace = workspaceQ.data
  const ledgerQ = useQuery({
    queryKey: ['ledger-transactions', workspace?.statement.period_start, workspace?.statement.period_end],
    queryFn: () => fetchLedgerTransactions(workspace!.statement.period_start, workspace!.statement.period_end),
    enabled: workspace !== undefined,
  })

  useEffect(() => {
    if (workspace?.lines.length && !workspace.lines.some((line) => line.id === selectedLineId)) {
      setSelectedLineId(workspace.lines.find((line) => line.status === 'unmatched')?.id ?? workspace.lines[0].id)
    }
  }, [selectedLineId, workspace?.lines])

  const selectedLine = workspace?.lines.find((line) => line.id === selectedLineId) ?? null
  const matchedLedgerIds = new Set(workspace?.matches.map((match) => match.ledger_transaction_id) ?? [])
  const availableLedger = useMemo(
    () =>
      (ledgerQ.data ?? []).filter(
        (transaction) =>
          !matchedLedgerIds.has(transaction.id) &&
          transaction.postings.some((posting) => posting.account_id === workspace?.statement.account_id),
      ),
    [ledgerQ.data, workspace?.matches, workspace?.statement.account_id],
  )

  function invalidateWorkspace() {
    void queryClient.invalidateQueries({ queryKey: ['recon-workspace', statementId] })
    void queryClient.invalidateQueries({ queryKey: ['recon-statements', accountId] })
  }

  const suggestMut = useMutation({
    mutationFn: () => suggestReconMatches(statementId!),
    onSuccess: (proposals) => {
      setSuggestions(
        proposals.reduce<Record<number, typeof proposals>>((byLine, proposal) => {
          byLine[proposal.line_id] = [...(byLine[proposal.line_id] ?? []), proposal]
          return byLine
        }, {}),
      )
    },
  })
  const confirmMut = useMutation({
    mutationFn: ({ lineId, ledgerId, method }: { lineId: number; ledgerId: number; method: 'suggested' | 'manual' }) =>
      confirmReconMatch(statementId!, lineId, ledgerId, method),
    onSuccess: invalidateWorkspace,
  })
  const ignoreMut = useMutation({
    mutationFn: (lineId: number) => ignoreReconLine(statementId!, lineId),
    onSuccess: invalidateWorkspace,
  })
  const adjustMut = useMutation({
    mutationFn: () =>
      createReconAdjustment(statementId!, {
        line_id: selectedLine!.id,
        counterpart_account_id: Number(counterpartAccountId),
        category,
        payee: selectedLine!.payee,
        notes: selectedLine!.narration,
      }),
    onSuccess: () => {
      setAdjusting(false)
      invalidateWorkspace()
    },
  })
  const closeMut = useMutation({ mutationFn: () => softCloseReconStatement(statementId!), onSuccess: invalidateWorkspace })
  const reopenMut = useMutation({ mutationFn: () => reopenReconStatement(statementId!), onSuccess: invalidateWorkspace })

  const error = [suggestMut, confirmMut, ignoreMut, adjustMut, closeMut, reopenMut].find((mutation) => mutation.isError)?.error

  if (accountsQ.isPending) return <PageLoading lines={3} showFooterBlock />
  if (accountsQ.isError) return <PageError title="Failed to load accounts" message={String(accountsQ.error)} />

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Control book"
        title="Reconciliation"
        description="Match each statement line to the double-entry ledger before closing the period."
        actions={
          <button
            type="button"
            onClick={() => void workspaceQ.refetch()}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
          >
            <RefreshCw className={`size-3.5 ${workspaceQ.isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      />

      <Panel>
        <label className="flex max-w-sm flex-col gap-1 text-sm font-medium text-zinc-700">
          Account
          <select
            value={accountId ?? ''}
            onChange={(event) => { setAccountId(Number(event.target.value)); setStatementId(null); setSuggestions({}) }}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            {accountsQ.data?.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}
          </select>
        </label>
      </Panel>

      {statementsQ.isPending ? <PageLoading lines={2} /> : statementsQ.isError ? (
        <PageError title="Failed to load statements" message={String(statementsQ.error)} />
      ) : (statementsQ.data ?? []).length === 0 ? (
        <Panel><p className="text-sm text-zinc-500">No statements for this account. Import or create a statement workspace to begin reconciliation.</p></Panel>
      ) : (
        <>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {statementsQ.data?.map((statement) => (
              <button
                key={statement.id}
                type="button"
                onClick={() => { setStatementId(statement.id); setSuggestions({}) }}
                className={`min-w-56 rounded-xl border p-3 text-left ${statement.id === statementId ? 'border-emerald-500 bg-emerald-50' : 'border-zinc-200 bg-white hover:bg-zinc-50'}`}
              >
                <div className="flex items-center justify-between gap-2"><p className="text-sm font-semibold text-zinc-800">{statement.period_start} – {statement.period_end}</p><StatusBadge status={statement.status} /></div>
                <p className="mt-1 text-xs text-zinc-500">Closing {formatPaise(statement.closing_balance_paise)}</p>
              </button>
            ))}
          </div>

          {workspaceQ.isPending ? <PageLoading lines={4} /> : workspaceQ.isError || !workspace ? (
            <PageError title="Failed to load workspace" message={String(workspaceQ.error)} />
          ) : (
            <>
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
                <Panel className="p-0">
                  <div className="flex items-center justify-between border-b border-zinc-100 px-4 py-3">
                    <p className="text-sm font-semibold text-zinc-800">Statement lines</p>
                    <button type="button" onClick={() => suggestMut.mutate()} disabled={suggestMut.isPending || workspace.statement.status !== 'open'} className="flex items-center gap-1 rounded-lg bg-zinc-900 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-zinc-700 disabled:opacity-50">
                      <Sparkles className="size-3.5" /> {suggestMut.isPending ? 'Finding…' : 'Suggest matches'}
                    </button>
                  </div>
                  <div className="max-h-[32rem] divide-y divide-zinc-100 overflow-y-auto">
                    {workspace.lines.map((line) => (
                      <button key={line.id} type="button" onClick={() => { setSelectedLineId(line.id); setAdjusting(false); setManualLedgerId('') }} className={`w-full px-4 py-3 text-left hover:bg-zinc-50 ${selectedLineId === line.id ? 'bg-emerald-50/70' : ''}`}>
                        <div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium text-zinc-800">{line.payee ?? line.narration ?? 'Unlabelled line'}</p><p className="mt-0.5 text-xs text-zinc-500">{line.tx_date} · {line.direction === 'in' ? 'Inflow' : 'Outflow'}</p></div><div className="text-right"><p className="text-sm font-semibold text-zinc-800">{formatPaise(line.amount_paise)}</p><StatusBadge status={line.status} /></div></div>
                      </button>
                    ))}
                  </div>
                </Panel>

                <Panel>
                  {!selectedLine ? <p className="py-20 text-center text-sm text-zinc-500">Select a statement line to review it.</p> : <LineWorkspace
                    line={selectedLine}
                    statementOpen={workspace.statement.status === 'open'}
                    suggestions={suggestions[selectedLine.id] ?? []}
                    ledger={availableLedger}
                    manualLedgerId={manualLedgerId}
                    setManualLedgerId={setManualLedgerId}
                    onConfirmSuggested={(ledgerId) => confirmMut.mutate({ lineId: selectedLine.id, ledgerId, method: 'suggested' })}
                    onIgnore={() => ignoreMut.mutate(selectedLine.id)}
                    onShowAdjust={() => setAdjusting(true)}
                    onManualMatch={() => confirmMut.mutate({ lineId: selectedLine.id, ledgerId: Number(manualLedgerId), method: 'manual' })}
                    busy={confirmMut.isPending || ignoreMut.isPending || adjustMut.isPending}
                  />}
                  {adjusting && selectedLine ? (
                    <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
                      <p className="font-semibold text-amber-900">Post an adjustment</p>
                      <p className="mt-1 text-xs text-amber-800">Creates an explicit ledger entry, then matches it to this statement line.</p>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <label className="text-xs font-medium text-zinc-700">Counterpart account<select value={counterpartAccountId} onChange={(event) => setCounterpartAccountId(event.target.value)} className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"><option value="">Select account…</option>{accountsQ.data?.filter((account) => account.id !== workspace.statement.account_id).map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
                        <label className="text-xs font-medium text-zinc-700">Category<input value={category} onChange={(event) => setCategory(event.target.value)} className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm" /></label>
                      </div>
                      <div className="mt-3 flex gap-2"><button type="button" onClick={() => adjustMut.mutate()} disabled={!counterpartAccountId || !category.trim() || adjustMut.isPending} className="rounded-lg bg-amber-600 px-3 py-2 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50">Post adjustment</button><button type="button" onClick={() => setAdjusting(false)} className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs font-medium text-zinc-700">Cancel</button></div>
                    </div>
                  ) : null}
                </Panel>
              </div>

              <Panel className={`flex flex-wrap items-center justify-between gap-4 border ${workspace.period_status.can_soft_close ? 'border-emerald-200 bg-emerald-50/50' : 'border-zinc-200'}`}>
                <div className="flex items-center gap-3"><Scale className={`size-5 ${workspace.period_status.can_soft_close ? 'text-emerald-600' : 'text-zinc-400'}`} /><div><p className="text-sm font-semibold text-zinc-800">Statement {formatPaise(workspace.period_status.statement_closing_balance_paise)} · Ledger {formatPaise(workspace.period_status.ledger_balance_paise)}</p><p className="text-xs text-zinc-500">Delta {formatPaise(workspace.period_status.balance_difference_paise)} · {workspace.period_status.unmatched_line_count} unmatched lines · {workspace.period_status.unmatched_ledger_count} unmatched ledger entries</p></div></div>
                {workspace.statement.status === 'reconciled' ? <button type="button" onClick={() => reopenMut.mutate()} disabled={reopenMut.isPending} className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm font-semibold text-zinc-700">Reopen period</button> : <button type="button" onClick={() => closeMut.mutate()} disabled={!workspace.period_status.can_soft_close || closeMut.isPending} className="flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-40"><Check className="size-4" /> Soft close</button>}
              </Panel>
            </>
          )}
        </>
      )}
      {error ? <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{String(error)}</p> : null}
    </div>
  )
}

function LineWorkspace({
  line, statementOpen, suggestions, ledger, manualLedgerId, setManualLedgerId, onConfirmSuggested, onIgnore, onShowAdjust, onManualMatch, busy,
}: {
  line: ReconStatementLine
  statementOpen: boolean
  suggestions: Array<{ ledger_transaction_id: number; score: number; reasons: string[] }>
  ledger: Array<{ id: number; date: string; payee: string | null; amount_paise: number }>
  manualLedgerId: string
  setManualLedgerId: (value: string) => void
  onConfirmSuggested: (ledgerId: number) => void
  onIgnore: () => void
  onShowAdjust: () => void
  onManualMatch: () => void
  busy: boolean
}) {
  const canAct = statementOpen && line.status === 'unmatched'
  return <div>
    <div className="flex items-start justify-between gap-4 border-b border-zinc-100 pb-4"><div><p className="text-xs font-semibold uppercase tracking-wide text-zinc-400">Selected statement line</p><p className="mt-1 text-lg font-semibold text-zinc-900">{line.payee ?? line.narration ?? 'Unlabelled line'}</p><p className="text-sm text-zinc-500">{line.tx_date} · {line.direction === 'in' ? 'Inflow' : 'Outflow'} · {formatPaise(line.amount_paise)}</p></div><StatusBadge status={line.status} /></div>
    {line.status === 'ignored' ? <p className="mt-4 text-sm text-zinc-500">Ignored{line.ignore_reason ? `: ${line.ignore_reason}` : '.'}</p> : null}
    {line.status === 'matched' ? <p className="mt-4 text-sm text-emerald-700">This line is confirmed against the ledger.</p> : null}
    {canAct ? <div className="mt-5 space-y-5">
      <div><p className="text-sm font-semibold text-zinc-800">Suggested matches</p>{suggestions.length === 0 ? <p className="mt-1 text-sm text-zinc-500">Run “Suggest matches” to search the ledger by amount, date, and payee.</p> : <div className="mt-2 space-y-2">{suggestions.map((proposal) => <div key={proposal.ledger_transaction_id} className="flex items-center justify-between gap-3 rounded-lg border border-zinc-200 p-3"><div><p className="text-sm font-medium text-zinc-800">Ledger transaction #{proposal.ledger_transaction_id}</p><p className="text-xs text-zinc-500">{proposal.reasons.join(' · ')} · {Math.round(proposal.score * 100)}% confidence</p></div><button type="button" onClick={() => onConfirmSuggested(proposal.ledger_transaction_id)} disabled={busy} className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-800 disabled:opacity-50">Confirm</button></div>)}</div>}</div>
      <div className="border-t border-zinc-100 pt-5"><p className="text-sm font-semibold text-zinc-800">Manual match</p><div className="mt-2 flex gap-2"><select value={manualLedgerId} onChange={(event) => setManualLedgerId(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"><option value="">Choose unmatched ledger entry…</option>{ledger.map((transaction) => <option key={transaction.id} value={transaction.id}>{transaction.date} · {transaction.payee ?? 'No payee'} · {formatPaise(transaction.amount_paise)}</option>)}</select><button type="button" onClick={onManualMatch} disabled={!manualLedgerId || busy} className="rounded-lg border border-emerald-200 px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-50">Match</button></div></div>
      <div className="flex flex-wrap gap-2 border-t border-zinc-100 pt-5"><button type="button" onClick={onIgnore} disabled={busy} className="flex items-center gap-1.5 rounded-lg border border-zinc-200 px-3 py-2 text-xs font-semibold text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"><X className="size-3.5" /> Ignore</button><button type="button" onClick={onShowAdjust} disabled={busy} className="rounded-lg border border-amber-200 px-3 py-2 text-xs font-semibold text-amber-700 hover:bg-amber-50 disabled:opacity-50">Adjust</button></div>
    </div> : null}
  </div>
}
