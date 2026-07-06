import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Upload } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  AddTransactionDrawer,
  type TransactionEditDraft,
} from '@/components/transactions/AddTransactionDrawer'
import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
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
  const [importOpen, setImportOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [categorySearch, setCategorySearch] = useState('')

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

  const categoryCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of allRows) {
      map.set(r.category, (map.get(r.category) ?? 0) + 1)
    }
    return map
  }, [allRows])

  const accountCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of allRows) {
      if (r.account) map.set(r.account, (map.get(r.account) ?? 0) + 1)
    }
    return map
  }, [allRows])

  const filteredCategories = useMemo(() => {
    const q = categorySearch.trim().toLowerCase()
    let list = categories
    if (q) list = list.filter((c) => c.toLowerCase().includes(q))
    return [...list].sort(
      (a, b) => (categoryCounts.get(b) ?? 0) - (categoryCounts.get(a) ?? 0),
    )
  }, [categories, categorySearch, categoryCounts])

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

  const activeFilterCount =
    selectedCategories.size +
    (accountFilter ? 1 : 0) +
    (txTypeFilter !== 'all' ? 1 : 0) +
    (hideTransfers && txTypeFilter === 'all' ? 1 : 0) +
    (activePreset === -1 && (startDate || endDate) ? 1 : 0)

  if (q.isPending) {
    return <PageLoading lines={3} showFooterBlock />
  }

  if (q.isError) {
    return (
      <PageError title="Failed to load transactions" message={<p className="text-sm">{String(q.error)}</p>} />
    )
  }

  return (
    <div className="flex h-[calc(100dvh-3rem)] flex-col gap-2 lg:h-[calc(100dvh-4rem)]">
      <AddTransactionDrawer
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false)
          setEditDraft(null)
        }}
        accounts={knownAccounts}
        editDraft={editDraft}
      />

      {/* Compact header + toolbar */}
      <div className="shrink-0 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-zinc-900">Transactions</h1>
            <p className="text-xs text-zinc-500">
              {rows.length === allRows.length
                ? `${allRows.length} row${allRows.length !== 1 ? 's' : ''}`
                : `${rows.length} of ${allRows.length}`}
              {rows.length > 0 ? (
                <>
                  {' · '}
                  <span className="text-red-700">DR {formatPaise(totalDebit)}</span>
                  {' · '}
                  <span className="text-emerald-700">CR {formatPaise(totalCredit)}</span>
                  {' · '}
                  <span className="font-medium text-zinc-800">
                    Net {formatPaise(totalDebit - totalCredit)}
                  </span>
                </>
              ) : null}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to="/transactions/templates"
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
            >
              Templates
            </Link>
            <Link
              to="/merchants"
              className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-700 hover:bg-zinc-50"
            >
              Merchants
            </Link>
            <button
              type="button"
              onClick={() => {
                setEditDraft(null)
                setDrawerOpen(true)
              }}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
            >
              Add
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200/80 bg-white px-3 py-2 shadow-sm ring-1 ring-zinc-900/[0.03]">
          <label className="flex items-center gap-1.5 text-xs text-zinc-600">
            Period
            <select
              value={activePreset >= 0 ? activePreset : 'custom'}
              onChange={(e) => {
                const v = e.target.value
                if (v !== 'custom') applyPreset(Number(v))
              }}
              className="rounded-md border border-zinc-200 bg-white py-1 pl-2 pr-7 text-xs font-medium text-zinc-800"
            >
              {activePreset === -1 ? <option value="custom">Custom range</option> : null}
              {DATE_PRESETS.map((p, idx) => (
                <option key={p.label} value={idx}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          <span className="hidden h-4 w-px bg-zinc-200 sm:block" aria-hidden />

          <div className="flex flex-wrap items-center gap-1">
            {(['all', 'debit', 'credit', 'transfer'] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTxTypeFilter(t)}
                className={`rounded-md px-2 py-1 text-xs font-medium transition ${
                  txTypeFilter === t
                    ? 'bg-emerald-100 text-emerald-900'
                    : 'text-zinc-600 hover:bg-zinc-100'
                }`}
              >
                {t === 'all' ? 'All' : t === 'debit' ? 'DR' : t === 'credit' ? 'CR' : 'Xfer'}
              </button>
            ))}
          </div>

          <span className="hidden h-4 w-px bg-zinc-200 sm:block" aria-hidden />

          <button
            type="button"
            onClick={() => setFiltersOpen((v) => !v)}
            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition ${
              filtersOpen || activeFilterCount > 0
                ? 'bg-zinc-100 text-zinc-900'
                : 'text-zinc-600 hover:bg-zinc-100'
            }`}
          >
            Filters
            {activeFilterCount > 0 ? (
              <span className="rounded-full bg-emerald-600 px-1.5 text-[10px] font-semibold text-white">
                {activeFilterCount}
              </span>
            ) : null}
            <ChevronDown
              className={`size-3.5 transition ${filtersOpen ? 'rotate-180' : ''}`}
              aria-hidden
            />
          </button>

          <button
            type="button"
            onClick={() => setImportOpen((v) => !v)}
            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition ${
              importOpen ? 'bg-emerald-100 text-emerald-900' : 'text-zinc-600 hover:bg-zinc-100'
            }`}
          >
            <Upload className="size-3.5" aria-hidden />
            Import
            <ChevronDown
              className={`size-3.5 transition ${importOpen ? 'rotate-180' : ''}`}
              aria-hidden
            />
          </button>

          {rows.length > 0 ? (
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-600">
                <input
                  ref={selectAllRef}
                  type="checkbox"
                  className="rounded border-zinc-300"
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  aria-label="Select all"
                />
                All
              </label>
              {selectedVisible.size > 0 ? (
                <>
                  <span className="text-xs text-zinc-500">{selectedVisible.size} selected</span>
                  <button
                    type="button"
                    disabled={del.isPending}
                    onClick={deleteSelected}
                    className="rounded-md border border-red-200 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                  >
                    {del.isPending ? 'Deleting…' : 'Delete'}
                  </button>
                </>
              ) : null}
            </div>
          ) : null}
        </div>

        {filtersOpen ? (
          <Panel padding={false}>
            <div className="space-y-3 p-3">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[auto_auto_1fr_auto] lg:items-end">
                <label className="flex flex-col gap-1 text-xs text-zinc-600">
                  From
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => {
                      setStartDate(e.target.value)
                      setActivePreset(-1)
                    }}
                    className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs text-zinc-600">
                  To
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => {
                      setEndDate(e.target.value)
                      setActivePreset(-1)
                    }}
                    className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                  />
                </label>
                {accountsInData.length > 0 ? (
                  <label className="flex flex-col gap-1 text-xs text-zinc-600">
                    Account
                    <select
                      value={accountFilter}
                      onChange={(e) => setAccountFilter(e.target.value)}
                      className="rounded-md border border-zinc-200 bg-white px-2 py-1.5 text-xs"
                    >
                      <option value="">All accounts</option>
                      {accountsInData.map((acct) => (
                        <option key={acct} value={acct}>
                          {acct} ({accountCounts.get(acct) ?? 0})
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
                {txTypeFilter === 'all' ? (
                  <label className="flex cursor-pointer items-center gap-2 pb-1.5 text-xs text-zinc-600 lg:pb-2">
                    <input
                      type="checkbox"
                      className="rounded border-zinc-300"
                      checked={hideTransfers}
                      onChange={(e) => setHideTransfers(e.target.checked)}
                    />
                    Hide transfers
                  </label>
                ) : null}
              </div>

              {categories.length > 0 ? (
                <div className="rounded-lg border border-zinc-100 bg-zinc-50/50 p-2.5">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium text-zinc-700">Categories</span>
                    <input
                      type="search"
                      value={categorySearch}
                      onChange={(e) => setCategorySearch(e.target.value)}
                      placeholder="Search…"
                      className="w-full max-w-[12rem] rounded-md border border-zinc-200 bg-white px-2 py-1 text-xs placeholder:text-zinc-400"
                    />
                  </div>

                  {selectedCategories.size > 0 ? (
                    <div className="mb-2 flex flex-wrap items-center gap-1.5">
                      {[...selectedCategories].sort().map((cat) => (
                        <button
                          key={cat}
                          type="button"
                          onClick={() => toggleCategory(cat)}
                          className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-900"
                        >
                          {cat}
                          <span className="text-emerald-600" aria-hidden>
                            ×
                          </span>
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={() => setSelectedCategories(new Set())}
                        className="text-[11px] font-medium text-zinc-500 hover:text-zinc-800"
                      >
                        Clear all
                      </button>
                    </div>
                  ) : (
                    <p className="mb-2 text-[11px] text-zinc-500">
                      Pick one or more — sorted by volume
                    </p>
                  )}

                  <div className="max-h-36 overflow-y-auto rounded-md border border-zinc-200 bg-white">
                    {filteredCategories.length === 0 ? (
                      <p className="px-3 py-4 text-center text-xs text-zinc-500">
                        No categories match
                      </p>
                    ) : (
                      <ul className="grid sm:grid-cols-2">
                        {filteredCategories.map((cat) => {
                          const checked = selectedCategories.has(cat)
                          const count = categoryCounts.get(cat) ?? 0
                          return (
                            <li key={cat}>
                              <label className="flex cursor-pointer items-center gap-2 border-b border-zinc-50 px-2.5 py-1.5 text-xs hover:bg-zinc-50 sm:border-r sm:border-zinc-50">
                                <input
                                  type="checkbox"
                                  className="rounded border-zinc-300"
                                  checked={checked}
                                  onChange={() => toggleCategory(cat)}
                                />
                                <span className="min-w-0 flex-1 truncate text-zinc-800">{cat}</span>
                                <span className="shrink-0 tabular-nums text-zinc-400">{count}</span>
                              </label>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </Panel>
        ) : null}

        {importOpen ? (
          <Panel padding={false}>
            <div className="flex flex-wrap items-end gap-3 p-3">
              <label className="flex min-w-[10rem] flex-1 flex-col gap-1 text-xs text-zinc-600">
                Account tag
                <select
                  value={importAccount}
                  onChange={(e) => setImportAccount(e.target.value)}
                  className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                >
                  <option value="">Detect from file</option>
                  {knownAccounts
                    .filter((a) => a.is_active)
                    .map((a) => (
                      <option key={a.id} value={a.name}>
                        {a.name}
                      </option>
                    ))}
                </select>
              </label>
              <label className="flex min-w-[8rem] flex-col gap-1 text-xs text-zinc-600">
                PDF / Excel password
                <input
                  type="password"
                  value={pdfPassword}
                  onChange={(e) => setPdfPassword(e.target.value)}
                  autoComplete="off"
                  placeholder="Optional"
                  className="rounded-md border border-zinc-200 px-2 py-1.5 text-xs"
                />
              </label>
              <input
                type="file"
                accept=".csv,.xlsx,.xlsm,.xls,.pdf"
                className="text-xs file:mr-2 file:rounded-md file:border-0 file:bg-emerald-50 file:px-2 file:py-1.5 file:text-xs file:font-medium file:text-emerald-900"
                disabled={upload.isPending}
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) {
                    setLastImport(null)
                    upload.mutate({
                      file: f,
                      pdfPassword: pdfPassword.trim() || undefined,
                      accountName: importAccount.trim() || undefined,
                    })
                  }
                  e.target.value = ''
                }}
              />
              {upload.isPending ? (
                <span className="text-xs text-zinc-500">Importing…</span>
              ) : null}
            </div>
            {lastImport ? (
              <p
                className={`border-t border-zinc-100 px-3 py-2 text-xs ${
                  lastImport.startsWith('Error') ? 'text-red-700' : 'text-zinc-600'
                }`}
              >
                {lastImport}
              </p>
            ) : null}
          </Panel>
        ) : null}

        {del.isError ? <p className="text-xs text-red-600">{String(del.error)}</p> : null}
      </div>

      {/* Ledger — fills remaining viewport */}
      <Panel variant="table" padding={false} className="min-h-0 flex-1 overflow-hidden">
        <div className="h-full overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500 shadow-sm">
              <tr>
                <th className="w-10 px-2 py-2.5 pl-3" aria-hidden />
                <th className="px-3 py-2.5">Date</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Category</th>
                <th className="px-3 py-2.5">Merchant</th>
                <th className="px-3 py-2.5">Account</th>
                <th className="px-3 py-2.5">Payment</th>
                <th className="px-3 py-2.5 text-right">Amount</th>
                <th className="w-20 px-3 py-2.5 text-right"> </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-sm text-zinc-500">
                    No transactions — use <strong>Import</strong> or{' '}
                    <button
                      type="button"
                      className="font-medium text-emerald-700 hover:underline"
                      onClick={() => {
                        setEditDraft(null)
                        setDrawerOpen(true)
                      }}
                    >
                      Add
                    </button>
                  </td>
                </tr>
              ) : (
                rows.map((r) => {
                  const isCredit = r.transaction_type === 'credit'
                  const isTransfer = r.transaction_type === 'transfer'
                  return (
                    <tr key={r.id} className="hover:bg-zinc-50/80">
                      <td className="w-10 px-2 py-2 pl-3 align-middle">
                        <input
                          type="checkbox"
                          className="rounded border-zinc-300"
                          checked={selectedVisible.has(r.id)}
                          onChange={() => toggleRow(r.id)}
                          aria-label={`Select ${r.id}`}
                        />
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums text-zinc-700">
                        {r.date}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                            isTransfer
                              ? 'bg-violet-50 text-violet-800'
                              : isCredit
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-red-50 text-red-700'
                          }`}
                        >
                          {isTransfer ? '⇄' : isCredit ? 'CR' : 'DR'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-zinc-800">{r.category}</td>
                      <td
                        className="max-w-[14rem] truncate px-3 py-2 text-zinc-600"
                        title={r.merchant ?? undefined}
                      >
                        {formatMerchantCell(r.merchant)}
                      </td>
                      <td className="px-3 py-2">
                        {r.account ? (
                          <button
                            type="button"
                            onClick={() =>
                              setAccountFilter(accountFilter === r.account ? '' : (r.account ?? ''))
                            }
                            className={`rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${
                              accountFilter === r.account
                                ? 'border-blue-500 bg-blue-50 text-blue-800'
                                : 'border-zinc-200 text-zinc-600 hover:bg-zinc-50'
                            }`}
                          >
                            {r.account}
                          </button>
                        ) : (
                          <span className="text-zinc-400">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-xs text-zinc-600">{r.payment_mode}</td>
                      <td
                        className={`whitespace-nowrap px-3 py-2 text-right text-sm font-medium tabular-nums ${
                          isTransfer
                            ? 'text-violet-800'
                            : isCredit
                              ? 'text-emerald-700'
                              : 'text-zinc-900'
                        }`}
                      >
                        {isCredit ? '+' : ''}
                        {formatPaise(r.amount_paise)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => {
                            setEditDraft({ row: r, peer: transferPeer(r, allRows) })
                            setDrawerOpen(true)
                          }}
                          className="text-xs font-medium text-emerald-700 hover:underline"
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
        </div>
      </Panel>
    </div>
  )
}
