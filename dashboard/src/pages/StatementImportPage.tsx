import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { MANUAL_TX_CATEGORIES } from '@/constants/transactionForm'
import { aggregateChartKindsByType } from '@/lib/statementImportChartKinds'
import {
  bulkDeleteStatementImportTransactions,
  createStatementImportRule,
  createStatementImportTransaction,
  deleteStatementImportRule,
  downloadStatementImportCsv,
  fetchLatestStatementImportSnapshot,
  fetchStatementImportGmailStatus,
  fetchStatementImportRules,
  fetchStatementImportTags,
  fetchStatementsImportNow,
  putStatementImportTags,
  updateStatementImportRule,
  updateStatementImportTransaction,
} from '@/lib/api'
import type {
  StatementImportRuleBody,
  StatementImportRuleOut,
  StatementImportSnapshotOut,
  StatementImportTransactionBody,
  StatementImportTransactionRow,
  StatementTagRuleBody,
} from '@/types/api'

type RuleDraft = StatementImportRuleBody & { id?: number }
type TxDraft = StatementImportTransactionBody & { id?: string }

const TX_KIND_OPTIONS = [
  { value: 'spend', label: 'Expense' },
  { value: 'payment', label: 'Bill paid' },
  { value: 'refund', label: 'Refund' },
  { value: 'fee', label: 'Fee' },
  { value: 'interest', label: 'Interest' },
  { value: 'cashback', label: 'Cashback' },
] as const

const EMPTY_RULE: RuleDraft = {
  bank: '',
  card: '',
  from_emails: [''],
  subject_contains: '',
  pdf_password: '',
  is_enabled: true,
  fetch_months: 6,
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

const TX_KIND_LABELS: Record<string, { label: string; className: string }> = {
  spend: { label: 'Expense', className: 'bg-zinc-100 text-zinc-800' },
  payment: { label: 'Bill paid', className: 'bg-blue-100 text-blue-900' },
  refund: { label: 'Refund', className: 'bg-violet-100 text-violet-900' },
  fee: { label: 'Fee', className: 'bg-amber-100 text-amber-900' },
  interest: { label: 'Interest', className: 'bg-orange-100 text-orange-900' },
  cashback: { label: 'Cashback', className: 'bg-emerald-100 text-emerald-900' },
}

const TX_KIND_CHART_COLORS: Record<string, string> = {
  spend: '#71717a',
  payment: '#2563eb',
  refund: '#7c3aed',
  fee: '#d97706',
  interest: '#ea580c',
  cashback: '#059669',
}

const FETCH_TOAST_MS = 6000

type FetchNotice = {
  variant: 'success' | 'info' | 'warning' | 'error'
  message: string
  skipped: Array<Record<string, string>>
}

function cardKey(bank: string, card: string): string {
  return `${bank}::${card}`
}

function parseCardKey(key: string): { bank: string; card: string } {
  const [bank, card] = key.split('::')
  return { bank: bank ?? '', card: card ?? '' }
}

function TxKindBadge({ kind }: { kind: string | null | undefined }) {
  const key = (kind ?? 'spend').toLowerCase()
  const meta = TX_KIND_LABELS[key] ?? TX_KIND_LABELS.spend
  return (
    <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-semibold ${meta.className}`}>
      {meta.label}
    </span>
  )
}

const CELL_INPUT =
  'w-full min-w-0 rounded border border-zinc-200 bg-white px-1.5 py-1 text-xs focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500'

type TxRowProps = {
  draft: TxDraft
  onDraftChange: (draft: TxDraft) => void
  onSave: () => void
  onCancel: () => void
  savePending: boolean
  selectable?: boolean
  selected?: boolean
  onToggleSelect?: () => void
  isNew?: boolean
  hideCardColumn?: boolean
}

function EditableTxRow({
  draft,
  onDraftChange,
  onSave,
  onCancel,
  savePending,
  selectable = false,
  selected = false,
  onToggleSelect,
  isNew = false,
  hideCardColumn = false,
}: TxRowProps) {
  return (
    <tr className="border-b border-emerald-100 bg-emerald-50/60">
      <td className="py-1.5 pr-2">
        {selectable && onToggleSelect ? (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggleSelect}
            disabled={isNew}
            aria-label="Select row"
          />
        ) : null}
      </td>
      <td className="py-1.5 pr-2">
        <input
          type="date"
          className={CELL_INPUT}
          value={draft.date}
          onChange={(e) => onDraftChange({ ...draft, date: e.target.value })}
        />
      </td>
      <td className="py-1.5 pr-2">
        <select
          className={CELL_INPUT}
          value={draft.tx_kind ?? 'spend'}
          onChange={(e) => onDraftChange({ ...draft, tx_kind: e.target.value })}
        >
          {TX_KIND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </td>
      {hideCardColumn ? null : (
        <td className="py-1.5 pr-2">
          <input
            className={`${CELL_INPUT} mb-1`}
            placeholder="Bank"
            value={draft.bank}
            onChange={(e) => onDraftChange({ ...draft, bank: e.target.value })}
          />
          <input
            className={CELL_INPUT}
            placeholder="Card"
            value={draft.card}
            onChange={(e) => onDraftChange({ ...draft, card: e.target.value })}
          />
        </td>
      )}
      <td className="py-1.5 pr-2">
        <input
          className={CELL_INPUT}
          value={draft.description}
          onChange={(e) => onDraftChange({ ...draft, description: e.target.value })}
        />
      </td>
      <td className="py-1.5 pr-2">
        <input
          type="number"
          min={0}
          step="0.01"
          className={`${CELL_INPUT} text-right font-mono`}
          value={draft.amount}
          onChange={(e) =>
            onDraftChange({ ...draft, amount: parseFloat(e.target.value) || 0 })
          }
        />
      </td>
      <td className="py-1.5 pr-2">
        <select
          className={CELL_INPUT}
          value={draft.category ?? 'Other'}
          onChange={(e) => onDraftChange({ ...draft, category: e.target.value })}
        >
          {MANUAL_TX_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </td>
      <td className="py-1.5 pr-2">
        <input
          className={CELL_INPUT}
          value={draft.tags ?? ''}
          onChange={(e) => onDraftChange({ ...draft, tags: e.target.value })}
        />
      </td>
      <td className="py-1.5 pr-2">
        <input
          className={`${CELL_INPUT} font-mono`}
          placeholder="2026-01"
          value={draft.statement_period ?? ''}
          onChange={(e) => onDraftChange({ ...draft, statement_period: e.target.value })}
        />
      </td>
      <td className="py-1.5 text-right whitespace-nowrap">
        <button
          type="button"
          disabled={savePending}
          onClick={onSave}
          className="mr-2 text-emerald-700 hover:underline disabled:opacity-50"
        >
          {savePending ? 'Saving…' : 'Save'}
        </button>
        <button type="button" onClick={onCancel} className="text-zinc-600 hover:underline">
          Cancel
        </button>
      </td>
    </tr>
  )
}

type ReadOnlyTxRowProps = {
  t: StatementImportTransactionRow
  selected: boolean
  onToggleSelect: () => void
  onEdit: () => void
  isEditingOther: boolean
  hideCardColumn?: boolean
}

function ReadOnlyTxRow({
  t,
  selected,
  onToggleSelect,
  onEdit,
  isEditingOther,
  hideCardColumn = false,
}: ReadOnlyTxRowProps) {
  return (
    <tr
      className={`border-b border-zinc-100 ${isEditingOther ? 'opacity-50' : 'cursor-pointer hover:bg-zinc-50/80'}`}
      onDoubleClick={() => {
        if (!isEditingOther) onEdit()
      }}
      title="Double-click to edit"
    >
      <td className="py-2 pr-2" onDoubleClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          aria-label={`Select ${t.description}`}
        />
      </td>
      <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs">{t.date}</td>
      <td className="py-2 pr-3">
        <TxKindBadge kind={t.tx_kind} />
      </td>
      {hideCardColumn ? null : (
        <td className="py-2 pr-3 text-xs">
          {t.bank}
          <br />
          <span className="text-zinc-500">{t.card}</span>
        </td>
      )}
      <td className="max-w-[240px] truncate py-2 pr-3" title={t.description}>
        {t.description}
      </td>
      <td
        className={`whitespace-nowrap py-2 pr-3 text-right font-mono text-xs ${
          t.tx_kind === 'payment' || t.tx_kind === 'refund' || t.tx_kind === 'cashback'
            ? 'text-emerald-700'
            : t.tx_kind === 'fee' || t.tx_kind === 'interest'
              ? 'text-amber-800'
              : 'text-zinc-900'
        }`}
      >
        {formatAmount(t.amount)}
      </td>
      <td className="py-2 pr-3 text-xs text-zinc-600">{t.category ?? '—'}</td>
      <td className="py-2 pr-3 text-xs text-zinc-600">{t.tags || '—'}</td>
      <td className="py-2 pr-3 font-mono text-xs text-zinc-500">{t.statement_period}</td>
      <td className="py-2 text-right" onDoubleClick={(e) => e.stopPropagation()}>
        <button type="button" className="text-emerald-700 hover:underline" onClick={onEdit}>
          Edit
        </button>
      </td>
    </tr>
  )
}

function FetchToast({
  notice,
  onDismiss,
}: {
  notice: FetchNotice
  onDismiss: () => void
}) {
  const styles = {
    success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    info: 'border-zinc-200 bg-white text-zinc-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-900',
    error: 'border-red-200 bg-red-50 text-red-900',
  }[notice.variant]

  return (
    <div
      role="status"
      className={`pointer-events-auto w-full max-w-md rounded-xl border px-4 py-3 shadow-lg ${styles}`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium leading-snug">{notice.message}</p>
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 text-lg leading-none opacity-60 hover:opacity-100"
          aria-label="Dismiss"
        >
          ×
        </button>
      </div>
      {notice.skipped.length > 0 ? (
        <ul className="mt-2 max-h-28 space-y-1 overflow-y-auto text-xs opacity-90">
          {notice.skipped.slice(0, 8).map((s, i) => (
            <li key={`${s.reason}-${s.gmail_message_id ?? s.rule_id ?? i}`}>
              <span className="font-medium">{s.reason}</span>
              {s.bank ? ` · ${s.bank}` : ''}
              {s.reason === 'no_emails_in_window' && s.fetch_months
                ? ` (try increasing fetch months, currently ${s.fetch_months})`
                : ''}
            </li>
          ))}
          {notice.skipped.length > 8 ? (
            <li className="text-zinc-500">+{notice.skipped.length - 8} more</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  )
}

function fyStartIso(): string {
  const now = new Date()
  const year = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1
  return `${year}-04-01`
}

function fyLabel(): string {
  const now = new Date()
  const startYear = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1
  const endYear = (startYear + 1) % 100
  return `${startYear}-${String(endYear).padStart(2, '0')}`
}

type InterestLeakageStats = {
  count: number
  total: number
  fyTotal: number
  byCard: Array<{ key: string; bank: string; card: string; amount: number; count: number }>
  byPeriod: Array<{ period: string; amount: number }>
}

function computeInterestLeakage(rows: StatementImportTransactionRow[]): InterestLeakageStats {
  const fyStart = fyStartIso()
  let total = 0
  let fyTotal = 0
  let count = 0
  const byCard = new Map<string, { bank: string; card: string; amount: number; count: number }>()
  const byPeriod = new Map<string, number>()

  for (const t of rows) {
    if ((t.tx_kind ?? '').toLowerCase() !== 'interest') continue
    const amt = Math.abs(t.amount)
    count += 1
    total += amt
    if (t.date >= fyStart) fyTotal += amt

    const k = cardKey(t.bank, t.card)
    const cur = byCard.get(k) ?? { bank: t.bank, card: t.card, amount: 0, count: 0 }
    cur.amount += amt
    cur.count += 1
    byCard.set(k, cur)

    if (t.statement_period) {
      byPeriod.set(t.statement_period, (byPeriod.get(t.statement_period) ?? 0) + amt)
    }
  }

  return {
    count,
    total,
    fyTotal,
    byCard: [...byCard.entries()]
      .map(([key, v]) => ({ key, ...v }))
      .sort((a, b) => b.amount - a.amount),
    byPeriod: [...byPeriod.entries()]
      .map(([period, amount]) => ({ period, amount }))
      .sort((a, b) => a.period.localeCompare(b.period)),
  }
}

function InterestLeakagePanel({
  stats,
  scopedStats,
  hasActiveFilters,
  onViewInterest,
}: {
  stats: InterestLeakageStats
  scopedStats: InterestLeakageStats
  hasActiveFilters: boolean
  onViewInterest: () => void
}) {
  if (stats.count === 0) {
    return (
      <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50/50 px-4 py-3 text-sm text-emerald-900">
        No interest charges detected in parsed statements — carry no balance past due date to keep it that way.
      </div>
    )
  }

  const periodChartData = stats.byPeriod.map((d) => ({
    period: d.period,
    amount: d.amount,
    label: d.period,
  }))

  return (
    <div className="mb-6 space-y-4">
      <div className="rounded-xl border border-orange-200 bg-gradient-to-br from-orange-50/80 via-white to-white p-4 ring-1 ring-orange-900/5">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-orange-950">Credit card interest leakage</h3>
            <p className="mt-0.5 text-xs text-orange-900/80">
              Extra money paid on revolving balances — transactions classified as{' '}
              <span className="font-medium">Interest</span> ({stats.count} charge
              {stats.count === 1 ? '' : 's'})
            </p>
          </div>
          <button
            type="button"
            onClick={onViewInterest}
            className="shrink-0 rounded-lg border border-orange-200 bg-white px-3 py-1.5 text-xs font-medium text-orange-900 hover:bg-orange-50"
          >
            View interest rows
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <KpiCard
            tone="spending"
            label="Interest paid (all time)"
            value={formatAmount(stats.total)}
            hint="Total finance charges across all parsed statements"
          />
          <KpiCard
            tone="spending"
            label={`Interest this FY (${fyLabel()})`}
            value={formatAmount(stats.fyTotal)}
            hint="Since 1 April — avoidable cost of carrying balance"
          />
          {hasActiveFilters && scopedStats.count > 0 ? (
            <KpiCard
              tone="neutral"
              label="In current filter"
              value={formatAmount(scopedStats.total)}
              hint={`${scopedStats.count} interest row(s) in filtered view`}
            />
          ) : (
            <KpiCard
              tone="neutral"
              label="Cards with interest"
              value={String(stats.byCard.length)}
              hint={stats.byCard.map((c) => `${c.bank} · ${c.card}`).join(' · ')}
            />
          )}
        </div>

        {stats.fyTotal > 0 ? (
          <p className="mt-3 rounded-lg border border-red-200/80 bg-red-50/60 px-3 py-2 text-sm text-red-900">
            <span className="font-semibold">Leakage alert</span> — you&apos;ve paid{' '}
            <span className="font-semibold tabular-nums">{formatAmount(stats.fyTotal)}</span> in credit
            card interest this financial year. Paying the full statement balance before the due date stops
            future interest.
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-zinc-200 bg-white p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Interest by card
          </h4>
          <ul className="mt-3 space-y-2">
            {stats.byCard.map((c) => {
              const pct = stats.total > 0 ? Math.round((c.amount / stats.total) * 100) : 0
              return (
                <li key={c.key}>
                  <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                    <span className="font-medium text-zinc-900">
                      {c.bank} · {c.card}
                    </span>
                    <span className="shrink-0 font-mono text-xs font-semibold text-orange-800">
                      {formatAmount(c.amount)}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-zinc-100">
                    <div
                      className="h-full rounded-full bg-orange-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <p className="mt-0.5 text-xs text-zinc-500">
                    {c.count} charge{c.count === 1 ? '' : 's'} · {pct}% of total leakage
                  </p>
                </li>
              )
            })}
          </ul>
        </div>

        {periodChartData.length > 1 ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Interest by statement month
            </h4>
            <div className="mt-3 h-[200px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={periodChartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <XAxis dataKey="period" tick={{ fontSize: 10 }} interval={0} angle={-25} textAnchor="end" height={52} />
                  <YAxis tick={{ fontSize: 10 }} width={48} tickFormatter={(v) => `₹${Number(v).toLocaleString('en-IN')}`} />
                  <Tooltip
                    formatter={(value) => [
                      `₹${Number(value ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
                      'Interest',
                    ]}
                  />
                  <Bar dataKey="amount" fill="#ea580c" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : periodChartData.length === 1 ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Statement month
            </h4>
            <p className="mt-3 text-2xl font-semibold tabular-nums text-orange-800">
              {formatAmount(periodChartData[0].amount)}
            </p>
            <p className="text-xs text-zinc-500">{periodChartData[0].period}</p>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function TypeBreakdownCharts({ rows }: { rows: StatementImportTransactionRow[] }) {
  const chartData = useMemo(() => {
    const sums = aggregateChartKindsByType(rows)
    return TX_KIND_OPTIONS.filter((o) => o.value !== 'refund')
      .map((o) => ({
        kind: o.value,
        label: o.label,
        count: sums[o.value]?.count ?? 0,
        amount: sums[o.value]?.amount ?? 0,
        fill: TX_KIND_CHART_COLORS[o.value],
      }))
      .filter((d) => d.count > 0)
  }, [rows])

  if (chartData.length === 0) return null

  const totalAmount = chartData.reduce((s, d) => s + d.amount, 0)

  return (
    <div className="mb-6 grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Amount by type
        </h3>
        <div className="h-[220px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                dataKey="amount"
                nameKey="label"
                cx="50%"
                cy="50%"
                innerRadius="52%"
                outerRadius="78%"
                paddingAngle={2}
                stroke="#fff"
                strokeWidth={2}
              >
                {chartData.map((d) => (
                  <Cell key={d.kind} fill={d.fill} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value) => [
                  `₹${Number(value ?? 0).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`,
                  'Amount',
                ]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-600">
          {chartData.map((d) => (
            <li key={d.kind} className="flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: d.fill }} />
              {d.label}: {formatAmount(d.amount)}
            </li>
          ))}
        </ul>
      </div>
      <div className="rounded-xl border border-zinc-200 bg-white p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Count by type
        </h3>
        <div className="h-[220px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={48} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={32} />
              <Tooltip
                formatter={(value, name) => {
                  if (name === 'count') return [value, 'Transactions']
                  return [value, name]
                }}
              />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {chartData.map((d) => (
                  <Cell key={d.kind} fill={d.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-zinc-500">
          Total volume: {formatAmount(totalAmount)} across {rows.length} row(s). Matched refunds
          are netted against expenses; unmatched refunds count as bill paid.
        </p>
      </div>
    </div>
  )
}

function FilterPills({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Array<{ value: string; label: string; count?: number }>
  onChange: (v: string) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium text-zinc-500">{label}</span>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`rounded-full px-3 py-1 text-xs font-medium transition ${
            value === o.value
              ? 'bg-emerald-700 text-white'
              : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200'
          }`}
        >
          {o.label}
          {o.count !== undefined ? ` (${o.count})` : ''}
        </button>
      ))}
    </div>
  )
}

export function StatementImportPage() {
  const qc = useQueryClient()
  const [ruleDraft, setRuleDraft] = useState<RuleDraft | null>(null)
  const [tagDrafts, setTagDrafts] = useState<StatementTagRuleBody[] | null>(null)
  const [periodFilter, setPeriodFilter] = useState<string>('all')
  const [cardFilter, setCardFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [fetchNotice, setFetchNotice] = useState<FetchNotice | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [txDraft, setTxDraft] = useState<TxDraft | null>(null)
  const selectAllRef = useRef<HTMLInputElement>(null)

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
    mutationFn: (force?: boolean) => fetchStatementsImportNow(force),
    onSuccess: (data) => {
      qc.setQueryData(['statement-import-snapshot'], {
        id: data.snapshot_id ?? 0,
        fetched_at: new Date().toISOString(),
        gmail_scanned: data.gmail_scanned,
        statements_parsed: data.statements_parsed,
        skipped: data.skipped,
        transactions: data.transactions,
      } satisfies StatementImportSnapshotOut)
      setSelected(new Set())
      const variant =
        data.statements_parsed > 0
          ? 'success'
          : data.transactions.length > 0
            ? 'info'
            : data.skipped.length > 0
              ? 'warning'
              : 'info'
      let message = `Scanned ${data.gmail_scanned} email(s) · parsed ${data.statements_parsed} statement(s) · ${data.transactions.length} transaction row(s)`
      if (data.skipped.length > 0) message += ` · skipped ${data.skipped.length}`
      if (data.statements_parsed === 0 && data.transactions.length > 0) {
        message += ' — showing saved data'
      }
      setFetchNotice({ variant, message, skipped: data.skipped })
    },
    onError: (err) => {
      setFetchNotice({
        variant: 'error',
        message: String(err),
        skipped: [],
      })
    },
  })

  useEffect(() => {
    if (!fetchNotice) return
    const t = window.setTimeout(() => setFetchNotice(null), FETCH_TOAST_MS)
    return () => window.clearTimeout(t)
  }, [fetchNotice])

  const syncSnapshot = (snap: StatementImportSnapshotOut) => {
    qc.setQueryData(['statement-import-snapshot'], snap)
    setSelected(new Set())
    setTxDraft(null)
    fetchMut.reset()
  }

  const saveTxMut = useMutation({
    mutationFn: async (draft: TxDraft) => {
      const body: StatementImportTransactionBody = {
        date: draft.date.trim(),
        bank: draft.bank.trim(),
        card: draft.card.trim(),
        description: draft.description.trim(),
        amount: Math.abs(Number(draft.amount) || 0),
        currency: draft.currency ?? 'INR',
        category: draft.category?.trim() || 'Other',
        tx_kind: draft.tx_kind ?? 'spend',
        tags: draft.tags?.trim() ?? '',
        statement_period: draft.statement_period?.trim() ?? '',
        gmail_message_id: draft.gmail_message_id?.trim() ?? '',
      }
      if (draft.id) {
        return updateStatementImportTransaction(draft.id, body)
      }
      return createStatementImportTransaction(body)
    },
    onSuccess: syncSnapshot,
  })

  const deleteTxMut = useMutation({
    mutationFn: (ids: string[]) => bulkDeleteStatementImportTransactions(ids),
    onSuccess: syncSnapshot,
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
        fetch_months: draft.fetch_months ?? 6,
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
    if (fetchMut.data !== undefined) return fetchMut.data.transactions
    return qSnapshot.data?.transactions ?? []
  }, [fetchMut.data, qSnapshot.data])

  const periods = useMemo(() => {
    const set = new Set(transactions.map((t) => t.statement_period).filter(Boolean))
    return ['all', ...Array.from(set).sort().reverse()]
  }, [transactions])

  const periodScopedTx = useMemo(() => {
    if (periodFilter === 'all') return transactions
    return transactions.filter((t) => t.statement_period === periodFilter)
  }, [transactions, periodFilter])

  const cardOptions = useMemo(() => {
    const map = new Map<string, { bank: string; card: string }>()
    for (const t of periodScopedTx) {
      const k = cardKey(t.bank, t.card)
      if (!map.has(k)) map.set(k, { bank: t.bank, card: t.card })
    }
    const counts = new Map<string, number>()
    for (const t of periodScopedTx) {
      const k = cardKey(t.bank, t.card)
      counts.set(k, (counts.get(k) ?? 0) + 1)
    }
    return [...map.entries()]
      .map(([k, v]) => [k, v, counts.get(k) ?? 0] as const)
      .sort((a, b) => `${a[1].bank} ${a[1].card}`.localeCompare(`${b[1].bank} ${b[1].card}`))
  }, [periodScopedTx])

  const filteredTx = useMemo(() => {
    let rows = periodScopedTx
    if (cardFilter !== 'all') {
      const { bank, card } = parseCardKey(cardFilter)
      rows = rows.filter((t) => t.bank === bank && t.card === card)
    }
    if (typeFilter !== 'all') {
      rows = rows.filter((t) => (t.tx_kind ?? 'spend') === typeFilter)
    }
    return [...rows].sort((a, b) => b.date.localeCompare(a.date))
  }, [periodScopedTx, cardFilter, typeFilter])

  const groupedByCard = useMemo(() => {
    const groups = new Map<string, StatementImportTransactionRow[]>()
    for (const t of filteredTx) {
      const k = cardKey(t.bank, t.card)
      const list = groups.get(k) ?? []
      list.push(t)
      groups.set(k, list)
    }
    return [...groups.entries()]
  }, [filteredTx])

  const typeFilterOptions = useMemo(() => {
    const counts: Record<string, number> = {}
    let scoped = periodScopedTx
    if (cardFilter !== 'all') {
      const { bank, card } = parseCardKey(cardFilter)
      scoped = scoped.filter((t) => t.bank === bank && t.card === card)
    }
    for (const t of scoped) {
      const k = t.tx_kind ?? 'spend'
      counts[k] = (counts[k] ?? 0) + 1
    }
    return [
      { value: 'all', label: 'All types', count: scoped.length },
      ...TX_KIND_OPTIONS.filter((o) => (counts[o.value] ?? 0) > 0).map((o) => ({
        value: o.value,
        label: o.label,
        count: counts[o.value],
      })),
    ]
  }, [periodScopedTx, cardFilter])

  const interestLeakage = useMemo(() => computeInterestLeakage(transactions), [transactions])
  const scopedInterestLeakage = useMemo(() => computeInterestLeakage(filteredTx), [filteredTx])
  const hasActiveFilters =
    cardFilter !== 'all' || typeFilter !== 'all' || periodFilter !== 'all'

  const visibleIds = useMemo(
    () => new Set(filteredTx.map((t) => t.id).filter(Boolean)),
    [filteredTx],
  )

  const selectedVisible = useMemo(
    () => new Set([...selected].filter((id) => visibleIds.has(id))),
    [selected, visibleIds],
  )

  const allSelected = filteredTx.length > 0 && selectedVisible.size === filteredTx.length

  useEffect(() => {
    const el = selectAllRef.current
    if (!el) return
    el.indeterminate = selectedVisible.size > 0 && selectedVisible.size < filteredTx.length
  }, [selectedVisible.size, filteredTx.length])

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelected((prev) => {
        const next = new Set(prev)
        for (const id of visibleIds) next.delete(id)
        return next
      })
    } else {
      setSelected((prev) => new Set([...prev, ...visibleIds]))
    }
  }

  const toggleRow = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const openNewTx = () => {
    const fromFilter = cardFilter !== 'all' ? parseCardKey(cardFilter) : null
    const first = qRules.data?.[0]
    setTxDraft({
      date: new Date().toISOString().slice(0, 10),
      bank: fromFilter?.bank ?? first?.bank ?? '',
      card: fromFilter?.card ?? first?.card ?? '',
      description: '',
      amount: 0,
      tx_kind: 'spend',
      category: 'Other',
      tags: '',
      statement_period: periodFilter !== 'all' ? periodFilter : '',
      gmail_message_id: '',
    })
  }

  const openEditTx = (t: StatementImportTransactionRow) => {
    if (!t.id) return
    setTxDraft({
      id: t.id,
      date: t.date,
      bank: t.bank,
      card: t.card,
      description: t.description,
      amount: Math.abs(t.amount),
      tx_kind: t.tx_kind ?? 'spend',
      category: t.category ?? 'Other',
      tags: t.tags ?? '',
      statement_period: t.statement_period ?? '',
      gmail_message_id: t.gmail_message_id ?? '',
    })
  }

  const handleDeleteSelected = () => {
    const ids = [...selectedVisible]
    if (ids.length === 0) return
    if (!window.confirm(`Delete ${ids.length} selected transaction(s)?`)) return
    deleteTxMut.mutate(ids)
  }

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

  const hideCardColumn = cardFilter !== 'all'

  return (
    <div className="space-y-10">
      {fetchNotice ? (
        <div className="pointer-events-none fixed right-4 top-4 z-[90] flex flex-col gap-2">
          <FetchToast notice={fetchNotice} onDismiss={() => setFetchNotice(null)} />
        </div>
      ) : null}

      <PageHero
        eyebrow="Import"
        title="Statement import"
        description="Fetch credit card statement PDFs from Gmail, parse with bank-specific parsers, and review transactions by card. Merchant categories come from the global Merchants mapping."
        actions={
          <div className="flex flex-wrap gap-2">
            <Link
              to="/merchants"
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50"
            >
              Merchants
            </Link>
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
              onClick={() => fetchMut.mutate(false)}
              disabled={fetchMut.isPending || !gmailOk || enabledRules.length === 0}
              className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {fetchMut.isPending ? 'Fetching…' : 'Fetch statements'}
            </button>
            <button
              type="button"
              onClick={() => fetchMut.mutate(true)}
              disabled={fetchMut.isPending || !gmailOk || enabledRules.length === 0}
              title="Re-process emails even if already fetched"
              className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50 disabled:opacity-50"
            >
              Re-fetch all
            </button>
          </div>
        }
      />

      {!gmailOk ? (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Gmail is not configured — set <code className="rounded bg-white px-1">GMAIL_CREDENTIALS_PATH</code> in
          API <code className="rounded bg-white px-1">.env</code> and run{' '}
          <code className="rounded bg-white px-1">scripts/setup_gmail.py</code>.
        </p>
      ) : null}

      <section>
        <SectionTitle>Parsed transactions</SectionTitle>
        {qSnapshot.data ? (
          <p className="mb-3 text-xs text-zinc-500">
            Last fetch: {qSnapshot.data.fetched_at} · {transactions.length} row(s) across{' '}
            {cardOptions.length} card(s)
          </p>
        ) : null}
        <Panel variant="table">
          {transactions.length > 0 ? (
            <InterestLeakagePanel
              stats={interestLeakage}
              scopedStats={scopedInterestLeakage}
              hasActiveFilters={hasActiveFilters}
              onViewInterest={() => setTypeFilter('interest')}
            />
          ) : null}

          <div className="mb-4 space-y-3">
            <FilterPills
              label="Card"
              value={cardFilter}
              onChange={setCardFilter}
              options={[
                { value: 'all', label: 'All cards', count: periodScopedTx.length },
                ...cardOptions.map(([k, v, count]) => ({
                  value: k,
                  label: `${v.bank} · ${v.card}`,
                  count,
                })),
              ]}
            />
            <div className="flex flex-wrap items-center gap-4">
              <FilterPills
                label="Type"
                value={typeFilter}
                onChange={setTypeFilter}
                options={typeFilterOptions}
              />
              <label className="text-xs text-zinc-600">
                Month
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
            </div>
          </div>

          {filteredTx.length > 0 ? <TypeBreakdownCharts rows={filteredTx} /> : null}

          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-zinc-500">{filteredTx.length} row(s)</span>
            {transactions.length > 0 ? (
              <>
                <button
                  type="button"
                  onClick={openNewTx}
                  className="rounded-lg border border-dashed border-zinc-300 px-3 py-1 text-sm text-zinc-700 hover:bg-zinc-50"
                >
                  + Add row
                </button>
                {selectedVisible.size > 0 ? (
                  <span className="text-xs text-zinc-600">{selectedVisible.size} selected</span>
                ) : null}
                <button
                  type="button"
                  onClick={handleDeleteSelected}
                  disabled={selectedVisible.size === 0 || deleteTxMut.isPending}
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-1 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                >
                  {deleteTxMut.isPending ? 'Deleting…' : 'Delete selected'}
                </button>
              </>
            ) : null}
          </div>
          {deleteTxMut.isError ? (
            <p className="mb-2 text-sm text-red-600">{String(deleteTxMut.error)}</p>
          ) : null}
          {saveTxMut.isError ? (
            <p className="mb-2 text-sm text-red-600">{String(saveTxMut.error)}</p>
          ) : null}
          <p className="mb-2 text-xs text-zinc-500">Double-click a row to edit inline.</p>
          {filteredTx.length === 0 && !(txDraft && !txDraft.id) ? (
            <p className="py-8 text-center text-sm text-zinc-500">
              No transactions yet. Configure card rules and click Fetch statements.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1000px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-zinc-600">
                    <th className="w-10 py-2 pr-2">
                      <input
                        ref={selectAllRef}
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleSelectAll}
                        aria-label="Select all visible transactions"
                      />
                    </th>
                    <th className="py-2 pr-3 font-medium">Date</th>
                    <th className="py-2 pr-3 font-medium">Type</th>
                    {hideCardColumn ? null : (
                      <th className="py-2 pr-3 font-medium">Bank / Card</th>
                    )}
                    <th className="py-2 pr-3 font-medium">Description</th>
                    <th className="py-2 pr-3 font-medium text-right">Amount</th>
                    <th className="py-2 pr-3 font-medium">Category</th>
                    <th className="py-2 pr-3 font-medium">Tags</th>
                    <th className="py-2 pr-3 font-medium">Period</th>
                    <th className="py-2 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {txDraft && !txDraft.id ? (
                    <EditableTxRow
                      draft={txDraft}
                      onDraftChange={setTxDraft}
                      onSave={() => saveTxMut.mutate(txDraft)}
                      onCancel={() => setTxDraft(null)}
                      savePending={saveTxMut.isPending}
                      isNew
                    />
                  ) : null}
                  {cardFilter === 'all'
                    ? groupedByCard.map(([key, rows]) => {
                        const { bank, card } = parseCardKey(key)
                        const colSpan = hideCardColumn ? 9 : 10
                        return (
                          <Fragment key={key}>
                            <tr className="border-y border-zinc-200 bg-zinc-50/90">
                              <td colSpan={colSpan} className="px-3 py-2.5">
                                <span className="text-sm font-semibold text-zinc-900">
                                  {bank} · {card}
                                </span>
                                <span className="ml-2 text-xs font-normal text-zinc-500">
                                  {rows.length} row(s)
                                </span>
                              </td>
                            </tr>
                            {rows.map((t) =>
                              txDraft?.id === t.id && txDraft ? (
                                <EditableTxRow
                                  key={t.id}
                                  draft={txDraft}
                                  onDraftChange={setTxDraft}
                                  onSave={() => saveTxMut.mutate(txDraft)}
                                  onCancel={() => setTxDraft(null)}
                                  savePending={saveTxMut.isPending}
                                  selectable
                                  selected={selectedVisible.has(t.id)}
                                  onToggleSelect={() => toggleRow(t.id)}
                                  hideCardColumn
                                />
                              ) : (
                                <ReadOnlyTxRow
                                  key={t.id}
                                  t={t}
                                  selected={selectedVisible.has(t.id)}
                                  onToggleSelect={() => toggleRow(t.id)}
                                  onEdit={() => openEditTx(t)}
                                  isEditingOther={Boolean(txDraft)}
                                  hideCardColumn
                                />
                              ),
                            )}
                          </Fragment>
                        )
                      })
                    : filteredTx.map((t) =>
                        txDraft?.id === t.id && txDraft ? (
                          <EditableTxRow
                            key={t.id}
                            draft={txDraft}
                            onDraftChange={setTxDraft}
                            onSave={() => saveTxMut.mutate(txDraft)}
                            onCancel={() => setTxDraft(null)}
                            savePending={saveTxMut.isPending}
                            selectable
                            selected={selectedVisible.has(t.id)}
                            onToggleSelect={() => toggleRow(t.id)}
                            hideCardColumn
                          />
                        ) : (
                          <ReadOnlyTxRow
                            key={t.id}
                            t={t}
                            selected={selectedVisible.has(t.id)}
                            onToggleSelect={() => toggleRow(t.id)}
                            onEdit={() => openEditTx(t)}
                            isEditingOther={Boolean(txDraft)}
                            hideCardColumn
                          />
                        ),
                      )}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </section>

      <section>
        <SectionTitle>Card rules</SectionTitle>
        <p className="mb-3 text-sm text-zinc-600">
          One rule per bank/card: sender addresses, optional subject filter, PDF password, and how
          many months of statements to fetch from Gmail.
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
                  <th className="py-2 pr-3 font-medium">Fetch months</th>
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
                    <td className="py-2 pr-3 text-xs text-zinc-600">
                      {r.fetch_months === 0 ? 'All' : (r.fetch_months ?? 6)}
                    </td>
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
                            fetch_months: r.fetch_months ?? 6,
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
              <label className="block text-xs font-medium text-zinc-600">
                Fetch last N months
                <input
                  type="number"
                  min={0}
                  max={60}
                  className="mt-1 w-full max-w-xs rounded-md border border-zinc-200 px-2 py-1.5 text-sm"
                  value={ruleDraft.fetch_months ?? 6}
                  onChange={(e) => {
                    const raw = e.target.value
                    const n = raw === '' ? 6 : parseInt(raw, 10)
                    setRuleDraft({
                      ...ruleDraft,
                      fetch_months: Number.isNaN(n)
                        ? 6
                        : Math.min(60, Math.max(0, n)),
                    })
                  }}
                />
                <span className="mt-1 block text-xs font-normal text-zinc-500">
                  0 = all available (up to 50 emails). Otherwise only statement emails since N
                  months ago are scanned.
                </span>
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
    </div>
  )
}
