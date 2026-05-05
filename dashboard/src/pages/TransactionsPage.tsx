import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  AddTransactionDrawer,
  type TransactionEditDraft,
} from '@/components/transactions/AddTransactionDrawer'
import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  bulkDeleteTransactions,
  fetchAccounts,
  fetchTransactions,
  importTransactionsFile,
} from '@/lib/api'
import { formatMerchantCell } from '@/lib/merchantDisplay'
import { formatPaise } from '@/lib/format'
import type { TransactionRow } from '@/types/api'

function transferPeer(row: TransactionRow, pool: TransactionRow[]): TransactionRow | null {
  if (row.transaction_type !== 'transfer' || !row.transfer_pair_id) {
    return null
  }
  return (
    pool.find((x) => x.id !== row.id && x.transfer_pair_id === row.transfer_pair_id) ?? null
  )
}


/** Return YYYY-MM-DD for the first day of month offset from today (0 = this month, -1 = last month). */
function monthStart(offset: number): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() + offset)
  return d.toISOString().slice(0, 10)
}

function monthEnd(offset: number): string {
  const d = new Date()
  d.setDate(1)
  d.setMonth(d.getMonth() + offset + 1)
  d.setDate(0) // last day of target month
  return d.toISOString().slice(0, 10)
}

const DATE_PRESETS = [
  { label: 'This month', start: () => monthStart(0), end: () => monthEnd(0) },
  { label: 'Last month', start: () => monthStart(-1), end: () => monthEnd(-1) },
  { label: 'Last 3 months', start: () => monthStart(-2), end: () => monthEnd(0) },
  { label: 'Last 6 months', start: () => monthStart(-5), end: () => monthEnd(0) },
  { label: 'This FY', start: () => {
    const now = new Date()
    const fyStart = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1
    return `${fyStart}-04-01`
  }, end: () => monthEnd(0) },
  { label: 'All time', start: () => '', end: () => '' },
] as const

export function TransactionsPage() {
  const qc = useQueryClient()
  const [lastImport, setLastImport] = useState<string | null>(null)
  const [pdfPassword, setPdfPassword] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const selectAllRef = useRef<HTMLInputElement>(null)
  const [activePreset, setActivePreset] = useState(5) // "All time" default
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<Set<string>>(new Set())
  const [txTypeFilter, setTxTypeFilter] = useState<'all' | 'debit' | 'credit' | 'transfer'>('all')
  const [hideTransfers, setHideTransfers] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editDraft, setEditDraft] = useState<TransactionEditDraft | null>(null)
  const [accountFilter, setAccountFilter] = useState<string>('') // '' = all
  const [importAccount, setImportAccount] = useState<string>('') // account to tag import with

  // Fetch known accounts for the import selector and filter list.
  const accountsQ = useQuery({
    queryKey: ['accounts'],
    queryFn: () => fetchAccounts(),
    staleTime: 60_000,
  })
  const knownAccounts = useMemo(() => accountsQ.data ?? [], [accountsQ.data])

  const q = useQuery({
    queryKey: ['transactions', startDate, endDate],
    queryFn: () =>
      fetchTransactions(5000, {
        startDate: startDate || undefined,
        endDate: endDate || undefined,
      }),
    staleTime: Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: false,
    refetchInterval: false,
  })

  const del = useMutation({
    mutationFn: bulkDeleteTransactions,
    onSuccess: () => {
      setSelected(new Set())
      void qc.invalidateQueries({ queryKey: ['transactions'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-alerts'] })
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
    },
  })

  const upload = useMutation({
    mutationKey: ['file-upload'],
    mutationFn: (input: { file: File; pdfPassword?: string; accountName?: string }) =>
      importTransactionsFile(input.file, {
        pdfPassword: input.pdfPassword,
        accountName: input.accountName,
      }),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ['transactions'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      const errPart =
        data.errors.length > 0
          ? ` First issues: row ${data.errors[0].row} — ${data.errors[0].message}`
          : ''
      setLastImport(
        `Imported ${data.imported} row(s).${data.failed > 0 ? ` Failed: ${data.failed}.` : ''}${errPart}`,
      )
      setPdfPassword('')
    },
    onError: (e) => {
      setLastImport(`Error: ${String(e)}`)
    },
  })

  const allRows = useMemo(() => q.data ?? [], [q.data])

  // Unique categories sorted alphabetically, derived from the full (unfiltered) dataset.
  const categories = useMemo(() => {
    const set = new Set(allRows.map((r) => r.category))
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [allRows])

  // Client-side filtering by category, transaction type, and account.
  const rows = useMemo(() => {
    let filtered = allRows
    if (selectedCategories.size > 0) {
      filtered = filtered.filter((r) => selectedCategories.has(r.category))
    }
    if (txTypeFilter === 'all') {
      if (hideTransfers) {
        filtered = filtered.filter((r) => r.transaction_type !== 'transfer')
      }
    } else {
      filtered = filtered.filter((r) => r.transaction_type === txTypeFilter)
    }
    if (accountFilter) {
      filtered = filtered.filter((r) => r.account === accountFilter)
    }
    return filtered
  }, [allRows, selectedCategories, txTypeFilter, hideTransfers, accountFilter])

  // Unique account names present in the fetched data (for filter pills).
  const accountsInData = useMemo(() => {
    const set = new Set(allRows.map((r) => r.account).filter(Boolean) as string[])
    return [...set].sort((a, b) => a.localeCompare(b))
  }, [allRows])

  const rowIds = useMemo(() => new Set(rows.map((r) => r.id)), [rows])
  const selectedVisible = useMemo(
    () => new Set([...selected].filter((id) => rowIds.has(id))),
    [selected, rowIds],
  )

  useEffect(() => {
    const el = selectAllRef.current
    if (!el) {
      return
    }
    el.indeterminate = selectedVisible.size > 0 && selectedVisible.size < rows.length
  }, [selectedVisible.size, rows.length])

  const allSelected = rows.length > 0 && selectedVisible.size === rows.length

  const toggleSelectAll = () => {
    if (rows.length === 0) {
      return
    }
    if (allSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(rows.map((r) => r.id)))
    }
  }

  const toggleRow = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const deleteSelected = () => {
    const ids = [...selectedVisible]
    if (ids.length === 0) {
      return
    }
    const n = ids.length
    if (
      !window.confirm(
        `Soft-delete ${n} transaction${n === 1 ? '' : 's'}? They will be excluded from totals and reports.`,
      )
    ) {
      return
    }
    del.mutate(ids)
  }

  const applyPreset = (idx: number) => {
    setActivePreset(idx)
    const preset = DATE_PRESETS[idx]
    setStartDate(preset.start())
    setEndDate(preset.end())
  }

  const toggleCategory = (cat: string) => {
    setSelectedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(cat)) {
        next.delete(cat)
      } else {
        next.add(cat)
      }
      return next
    })
  }

  // Summary stats
  const totalDebit = useMemo(
    () => rows.filter((r) => r.transaction_type === 'debit').reduce((s, r) => s + r.amount_paise, 0),
    [rows],
  )
  const totalCredit = useMemo(
    () => rows.filter((r) => r.transaction_type === 'credit').reduce((s, r) => s + r.amount_paise, 0),
    [rows],
  )
  const totalTransfer = useMemo(
    () => rows.filter((r) => r.transaction_type === 'transfer').reduce((s, r) => s + r.amount_paise, 0),
    [rows],
  )

  if (q.isPending) {
    return <PageLoading lines={3} showFooterBlock />
  }

  if (q.isError) {
    return (
      <PageError title="Failed to load transactions" message={<p className="text-sm">{String(q.error)}</p>} />
    )
  }

  return (
    <div className="space-y-10">
      <AddTransactionDrawer
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false)
          setEditDraft(null)
        }}
        accounts={knownAccounts}
        editDraft={editDraft}
      />
      <PageHero
        eyebrow="Cash flow"
        title="Transactions"
        description={`${allRows.length} transaction${allRows.length !== 1 ? 's' : ''} · reloads when filters change or after import / edit`}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              to="/transactions/templates"
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50"
            >
              Templates
            </Link>
            <button
              type="button"
              onClick={() => {
                setEditDraft(null)
                setDrawerOpen(true)
              }}
              className="rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-sm font-semibold text-emerald-900 shadow-sm transition hover:bg-emerald-50"
            >
              Add transaction
            </button>
          </div>
        }
      />

      <section>
        <SectionTitle>Import from file</SectionTitle>
        <Panel>
        <h2 className="sr-only">Import from file</h2>
        <p className="mt-1 text-sm text-zinc-600">
          Upload a <strong className="font-medium text-zinc-800">CSV</strong>,{' '}
          <strong className="font-medium text-zinc-800">Excel</strong> (
          <code className="text-xs">.xlsx</code> / <code className="text-xs">.xlsm</code> /{' '}
          <code className="text-xs">.xls</code>), or a{' '}
          <strong className="font-medium text-zinc-800">PDF</strong> bank statement.
          Bank statement preamble rows (account info, bank name) are automatically skipped.
          Debit and credit columns are detected separately.
          Merchant names are auto-categorized when possible.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm text-zinc-600">
            <span className="text-xs font-medium text-zinc-500">
              Account (tag all transactions in this file)
            </span>
            <select
              value={importAccount}
              onChange={(e) => setImportAccount(e.target.value)}
              className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              <option value="">— No account / detect from file —</option>
              {knownAccounts.filter((a) => a.is_active).map((a) => (
                <option key={a.id} value={a.name}>
                  {a.name}{a.institution ? ` (${a.institution})` : ''}
                </option>
              ))}
            </select>
            {knownAccounts.length === 0 && (
              <span className="text-xs text-zinc-400">
                Add accounts on the <a href="/accounts" className="underline">Accounts page</a> to enable tagging.
              </span>
            )}
          </label>
          <label className="flex flex-col gap-1 text-sm text-zinc-600">
            <span className="text-xs font-medium text-zinc-500">
              Password (encrypted PDF or Excel)
            </span>
            <input
              type="password"
              value={pdfPassword}
              onChange={(e) => setPdfPassword(e.target.value)}
              autoComplete="off"
              placeholder="Leave blank if file is not encrypted"
              className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800 shadow-sm placeholder:text-zinc-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm,.xls,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
            className="text-sm text-zinc-700 file:mr-3 file:rounded-md file:border-0 file:bg-emerald-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-emerald-900 hover:file:bg-emerald-100"
            disabled={upload.isPending}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) {
                setLastImport(null)
                const pw = pdfPassword.trim()
                const acct = importAccount.trim()
                upload.mutate({ file: f, pdfPassword: pw || undefined, accountName: acct || undefined })
              }
              e.target.value = ''
            }}
          />
          {upload.isPending ? (
            <span className="text-sm text-zinc-500">Importing...</span>
          ) : null}
        </div>
        {upload.isPending ? (
          <p className="mt-3 text-xs text-zinc-500">
            Watch the green bar at the top — large PDFs can take several minutes while LM Studio runs.
          </p>
        ) : null}
        {lastImport ? (
          <p
            className={`mt-3 text-sm ${lastImport.startsWith('Error') ? 'text-red-700' : 'text-zinc-700'}`}
          >
            {lastImport}
          </p>
        ) : null}
        </Panel>
      </section>

      {/* Filters */}
      <section>
        <SectionTitle>Filters</SectionTitle>
        <Panel>
          <div className="flex flex-wrap items-center gap-2">
            {DATE_PRESETS.map((p, idx) => (
              <button
                key={p.label}
                type="button"
                onClick={() => applyPreset(idx)}
                className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
                  activePreset === idx
                    ? 'border-emerald-600 bg-emerald-50 text-emerald-800'
                    : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-zinc-600">
              From
              <input
                type="date"
                value={startDate}
                onChange={(e) => { setStartDate(e.target.value); setActivePreset(-1) }}
                className="rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-800 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
            <label className="flex items-center gap-2 text-sm text-zinc-600">
              To
              <input
                type="date"
                value={endDate}
                onChange={(e) => { setEndDate(e.target.value); setActivePreset(-1) }}
                className="rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm text-zinc-800 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </label>
          </div>
          {/* Transaction type filter */}
          <div className="mt-4">
            <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">Type</span>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              {(['all', 'debit', 'credit', 'transfer'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTxTypeFilter(t)}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
                    txTypeFilter === t
                      ? t === 'credit'
                        ? 'border-emerald-600 bg-emerald-50 text-emerald-800'
                        : t === 'debit'
                          ? 'border-red-400 bg-red-50 text-red-800'
                          : t === 'transfer'
                            ? 'border-violet-500 bg-violet-50 text-violet-900'
                            : 'border-emerald-600 bg-emerald-50 text-emerald-800'
                      : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                  }`}
                >
                  {t === 'all'
                    ? 'All'
                    : t === 'debit'
                      ? 'Debits'
                      : t === 'credit'
                        ? 'Credits'
                        : 'Transfers'}
                </button>
              ))}
            </div>
            {txTypeFilter === 'all' ? (
              <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-zinc-600">
                <input
                  type="checkbox"
                  className="rounded border-zinc-300"
                  checked={hideTransfers}
                  onChange={(e) => setHideTransfers(e.target.checked)}
                />
                Hide internal transfers (ledger still stored)
              </label>
            ) : null}
          </div>

          {/* Account filter */}
          {accountsInData.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-3">
                <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">Account</span>
                {accountFilter && (
                  <button
                    type="button"
                    onClick={() => setAccountFilter('')}
                    className="text-xs font-medium text-emerald-700 hover:text-emerald-900"
                  >
                    Show all
                  </button>
                )}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {accountsInData.map((acct) => {
                  const isActive = accountFilter === acct
                  const count = allRows.filter((r) => r.account === acct).length
                  return (
                    <button
                      key={acct}
                      type="button"
                      onClick={() => setAccountFilter(isActive ? '' : acct)}
                      className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                        isActive
                          ? 'border-blue-500 bg-blue-50 text-blue-800'
                          : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                      }`}
                    >
                      {acct}
                      <span className={`ml-1 ${isActive ? 'text-blue-500' : 'text-zinc-400'}`}>
                        {count}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Category filter */}
          {categories.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-3">
                <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">Category</span>
                {selectedCategories.size > 0 && (
                  <button
                    type="button"
                    onClick={() => setSelectedCategories(new Set())}
                    className="text-xs font-medium text-emerald-700 hover:text-emerald-900"
                  >
                    Clear filters
                  </button>
                )}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {categories.map((cat) => {
                  const isActive = selectedCategories.has(cat)
                  const count = allRows.filter((r) => r.category === cat).length
                  return (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => toggleCategory(cat)}
                      className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                        isActive
                          ? 'border-emerald-600 bg-emerald-50 text-emerald-800'
                          : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                      }`}
                    >
                      {cat}
                      <span className={`ml-1 ${isActive ? 'text-emerald-600' : 'text-zinc-400'}`}>
                        {count}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {rows.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-4 text-sm">
              <span className="font-medium text-zinc-700">
                {rows.length}
                {selectedCategories.size > 0 || txTypeFilter !== 'all' || hideTransfers
                  ? ` of ${allRows.length}`
                  : ''}{' '}
                transactions
              </span>
              <span className="text-red-700">Debits: {formatPaise(totalDebit)}</span>
              <span className="text-emerald-700">Credits: {formatPaise(totalCredit)}</span>
              {totalTransfer > 0 ? (
                <span className="text-violet-700">Transfers: {formatPaise(totalTransfer)}</span>
              ) : null}
              <span className="font-semibold text-zinc-900">Net: {formatPaise(totalDebit - totalCredit)}</span>
            </div>
          )}
        </Panel>
      </section>

      {rows.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-zinc-200/80 bg-zinc-50/90 px-4 py-3 shadow-md shadow-zinc-900/5 ring-1 ring-zinc-900/[0.04]">
          <label className="flex cursor-pointer items-center gap-2.5 text-sm font-medium text-zinc-800">
            <input
              ref={selectAllRef}
              type="checkbox"
              className="h-4 w-4 rounded border-zinc-300 text-emerald-700 focus:ring-emerald-600"
              checked={allSelected}
              onChange={toggleSelectAll}
              aria-label="Select all transactions on this page"
            />
            <span>Select all</span>
          </label>
          {selectedVisible.size > 0 ? (
            <span className="text-sm tabular-nums text-zinc-600">
              {selectedVisible.size} selected
            </span>
          ) : (
            <span className="text-sm text-zinc-500">Select rows to delete</span>
          )}
          <button
            type="button"
            disabled={selectedVisible.size === 0 || del.isPending}
            className="ml-auto rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-800 shadow-sm transition hover:bg-red-50 disabled:pointer-events-none disabled:opacity-40"
            onClick={deleteSelected}
          >
            {del.isPending ? 'Deleting...' : 'Delete selected'}
          </button>
        </div>
      ) : null}

      {del.isError ? (
        <p className="text-sm text-red-600">{String(del.error)}</p>
      ) : null}

      <section>
        <SectionTitle>Ledger</SectionTitle>
        <Panel variant="table" padding={false}>
        <table className="w-full text-left text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="w-10 px-2 py-3 pl-4" aria-hidden />
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Merchant</th>
              <th className="px-4 py-3">Account</th>
              <th className="px-4 py-3">Payment</th>
              <th className="px-4 py-3 text-right">Amount</th>
              <th className="w-24 px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-zinc-500">
                  No transactions yet — import a file above or log via Discord{' '}
                  <code className="text-xs">/log</code>
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const isCredit = r.transaction_type === 'credit'
                const isTransfer = r.transaction_type === 'transfer'
                return (
                  <tr key={r.id} className="hover:bg-zinc-50/80">
                    <td className="w-10 px-2 py-2.5 pl-4 align-middle">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-zinc-300 text-emerald-700 focus:ring-emerald-600"
                        checked={selectedVisible.has(r.id)}
                        onChange={() => toggleRow(r.id)}
                        aria-label={`Select transaction ${r.id}`}
                      />
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-zinc-700">{r.date}</td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          isTransfer
                            ? 'bg-violet-50 text-violet-800'
                            : isCredit
                              ? 'bg-emerald-50 text-emerald-700'
                              : 'bg-red-50 text-red-700'
                        }`}
                        title={r.transfer_pair_id ? `Pair ${r.transfer_pair_id}` : undefined}
                      >
                        {isTransfer ? '⇄' : isCredit ? 'CR' : 'DR'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-zinc-800">{r.category}</td>
                    <td
                      className="max-w-[20rem] truncate px-4 py-2.5 text-zinc-600"
                      title={r.merchant ?? undefined}
                    >
                      {formatMerchantCell(r.merchant)}
                    </td>
                    <td className="px-4 py-2.5">
                      {r.account ? (
                        <button
                          type="button"
                          onClick={() => setAccountFilter(accountFilter === r.account ? '' : (r.account ?? ''))}
                          className={`rounded-full border px-2 py-0.5 text-xs font-medium transition ${
                            accountFilter === r.account
                              ? 'border-blue-500 bg-blue-50 text-blue-800'
                              : 'border-zinc-200 bg-zinc-50 text-zinc-600 hover:bg-zinc-100'
                          }`}
                        >
                          {r.account}
                        </button>
                      ) : (
                        <span className="text-zinc-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-zinc-600">{r.payment_mode}</td>
                    <td
                      className={`px-4 py-2.5 text-right font-medium tabular-nums ${
                        isTransfer
                          ? 'text-violet-800'
                          : isCredit
                            ? 'text-emerald-700'
                            : 'text-zinc-900'
                      }`}
                    >
                      {isCredit ? '+' : ''}{formatPaise(r.amount_paise)}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          setEditDraft({ row: r, peer: transferPeer(r, allRows) })
                          setDrawerOpen(true)
                        }}
                        className="rounded-lg border border-zinc-200 bg-white px-2.5 py-1 text-xs font-semibold text-zinc-700 shadow-sm transition hover:bg-zinc-50"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
        </Panel>
      </section>
    </div>
  )
}
