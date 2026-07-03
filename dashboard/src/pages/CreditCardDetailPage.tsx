import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { QueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { NavigateFunction } from 'react-router-dom'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { CreditCardStatementSummarySection } from '@/components/credit-cards/CreditCardStatementSummarySection'
import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  convertEmiToDebt,
  deleteCreditCard,
  deleteCreditCardEmi,
  fetchAccounts,
  fetchCcInterestLeakage,
  fetchCcLiveBalance,
  fetchCreditCard,
  fetchCreditCardEmis,
  fetchCreditCardStatements,
  fetchTransactions,
  payCcBill,
  postCreditCardEmi,
  putCreditCard,
  putCreditCardEmi,
  uploadCreditCardStatement,
} from '@/lib/api'
import { formatPaiseCompact } from '@/lib/format'
import type { AccountOut, CreditCardEmiOut, CreditCardOut, TransactionRow } from '@/types/api'


function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) {
    return null
  }
  return Math.round(n * 100)
}

function formatOptionalIsoDate(s: string | null | undefined): string {
  if (!s) return '—'
  const d = new Date(s.includes('T') ? s : `${s}T12:00:00`)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function optionalRupeesField(r: string): number | null {
  const t = r.trim()
  if (!t) return null
  return rupeesToPaise(t)
}

function CreditCardEditForm({
  card,
  cardId,
  navigate,
  queryClient,
}: {
  card: CreditCardOut
  cardId: number
  navigate: NavigateFunction
  queryClient: QueryClient
}) {
  const [name, setName] = useState(card.name)
  const [issuer, setIssuer] = useState(card.issuer ?? '')
  const [lastFour, setLastFour] = useState(card.last_four ?? '')
  const [limitRupees, setLimitRupees] = useState(String(card.credit_limit_paise / 100))
  const [balRupees, setBalRupees] = useState(
    card.current_balance_paise != null ? String(card.current_balance_paise / 100) : '',
  )
  const [notes, setNotes] = useState(card.notes ?? '')
  const [active, setActive] = useState(card.is_active)
  const [stmtDay, setStmtDay] = useState(card.statement_day != null ? String(card.statement_day) : '')
  const [dueDay, setDueDay] = useState(card.due_day != null ? String(card.due_day) : '')
  const [minDuePct, setMinDuePct] = useState(card.minimum_due_pct != null ? String(card.minimum_due_pct) : '')
  const [rewardRate, setRewardRate] = useState(card.reward_rate_pct != null ? String(card.reward_rate_pct) : '')
  const [detailsExpanded, setDetailsExpanded] = useState(false)

  const save = useMutation({
    mutationFn: () => {
      const lim = rupeesToPaise(limitRupees)
      if (lim == null) {
        throw new Error('Invalid credit limit')
      }
      const bal = balRupees.trim() === '' ? null : rupeesToPaise(balRupees)
      if (balRupees.trim() !== '' && bal == null) {
        throw new Error('Invalid balance')
      }
      const sd = stmtDay.trim() ? Number.parseInt(stmtDay, 10) : null
      const dd = dueDay.trim() ? Number.parseInt(dueDay, 10) : null
      const mdp = minDuePct.trim() ? Number.parseFloat(minDuePct) : null
      const rr = rewardRate.trim() ? Number.parseFloat(rewardRate) : null
      return putCreditCard(cardId, {
        name: name.trim() || undefined,
        issuer: issuer.trim() || null,
        last_four: lastFour.trim() || null,
        credit_limit_paise: lim,
        current_balance_paise: bal,
        notes: notes.trim() || null,
        is_active: active,
        statement_day: sd,
        due_day: dd,
        minimum_due_pct: mdp,
        reward_rate_pct: rr,
      })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['credit-card', cardId] })
      void queryClient.invalidateQueries({ queryKey: ['credit-cards'] })
    },
  })

  const delCard = useMutation({
    mutationFn: () => deleteCreditCard(cardId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['credit-cards'] })
      navigate('/credit-cards')
    },
  })

  const limitPaiseSummary = rupeesToPaise(limitRupees)
  const balPaiseSummary = balRupees.trim() === '' ? null : rupeesToPaise(balRupees)
  const detailsPanelId = 'credit-card-edit-details'
  const detailsTriggerId = 'credit-card-edit-details-trigger'

  return (
    <Panel padding={false} className="overflow-hidden rounded-lg">
      {!detailsExpanded ? (
        <div className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:gap-3 sm:px-4">
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold leading-tight text-zinc-900">
              {name.trim() || 'Untitled card'}
            </p>
            <p className="truncate text-xs text-zinc-500">
              {issuer.trim() || '—'}
              {lastFour ? ` · •••• ${lastFour}` : ''}
            </p>
          </div>
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm sm:justify-end">
            <span className="tabular-nums text-zinc-800">
              <span className="text-xs font-medium text-zinc-500">Limit </span>
              {limitPaiseSummary != null ? formatPaiseCompact(limitPaiseSummary) : '—'}
            </span>
            <span className="tabular-nums text-zinc-800">
              <span className="text-xs font-medium text-zinc-500">Balance </span>
              {balPaiseSummary != null ? formatPaiseCompact(balPaiseSummary) : '—'}
            </span>
            <span className="text-zinc-700">
              <span className="text-xs font-medium text-zinc-500">Status </span>
              {active ? 'Active' : 'Inactive'}
            </span>
          </div>
          <div className="flex shrink-0 border-t border-zinc-100 pt-2 sm:border-t-0 sm:pt-0">
            <button
              type="button"
              className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-100"
              aria-expanded={false}
              onClick={() => setDetailsExpanded(true)}
            >
              Details
            </button>
          </div>
        </div>
      ) : (
        <div id={detailsPanelId} role="region" aria-labelledby={detailsTriggerId}>
          <div className="flex justify-end border-b border-zinc-100 px-3 py-2 sm:px-4">
            <button
              type="button"
              id={detailsTriggerId}
              className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-100"
              aria-expanded={true}
              aria-controls={detailsPanelId}
              onClick={() => setDetailsExpanded(false)}
            >
              Less
            </button>
          </div>
          <form
            className="grid gap-4 p-4 pt-3 sm:grid-cols-2 lg:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault()
              save.mutate()
            }}
          >
            <label className="text-xs font-medium text-zinc-700">
              Name
              <input
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Issuer
              <input
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm"
                value={issuer}
                onChange={(e) => setIssuer(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Last 4 digits
              <input
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm"
                value={lastFour}
                onChange={(e) => setLastFour(e.target.value.replace(/\D/g, '').slice(0, 4))}
                inputMode="numeric"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Credit limit (₹)
              <input
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={limitRupees}
                onChange={(e) => setLimitRupees(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Current balance (₹)
              <input
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={balRupees}
                onChange={(e) => setBalRupees(e.target.value)}
                placeholder="Leave blank if unknown"
              />
            </label>
            <label className="flex flex-col text-xs font-medium text-zinc-700">
              <span>Active</span>
              <input
                type="checkbox"
                className="mt-2 h-4 w-4 rounded border-zinc-300 text-emerald-700"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
              />
            </label>
            <label className="sm:col-span-2 lg:col-span-3 text-xs font-medium text-zinc-700">
              Notes
              <textarea
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm shadow-sm"
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
            <div className="sm:col-span-2 lg:col-span-3 border-t border-zinc-100 pt-3">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Billing settings</p>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <label className="text-xs font-medium text-zinc-700">
                  Statement day
                  <input
                    className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"
                    inputMode="numeric"
                    value={stmtDay}
                    onChange={(e) => setStmtDay(e.target.value.replace(/\D/g, '').slice(0, 2))}
                    placeholder="e.g. 15"
                  />
                </label>
                <label className="text-xs font-medium text-zinc-700">
                  Due day
                  <input
                    className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"
                    inputMode="numeric"
                    value={dueDay}
                    onChange={(e) => setDueDay(e.target.value.replace(/\D/g, '').slice(0, 2))}
                    placeholder="e.g. 5"
                  />
                </label>
                <label className="text-xs font-medium text-zinc-700">
                  Min due %
                  <input
                    className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm tabular-nums"
                    inputMode="decimal"
                    value={minDuePct}
                    onChange={(e) => setMinDuePct(e.target.value)}
                    placeholder="5"
                  />
                </label>
                <label className="text-xs font-medium text-zinc-700">
                  Reward rate %
                  <input
                    className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm tabular-nums"
                    inputMode="decimal"
                    value={rewardRate}
                    onChange={(e) => setRewardRate(e.target.value)}
                    placeholder="1.5"
                  />
                </label>
              </div>
            </div>
            <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-3">
              <button
                type="submit"
                disabled={save.isPending}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-50"
              >
                Save
              </button>
              <button
                type="button"
                disabled={delCard.isPending}
                className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-semibold text-red-800 shadow-sm hover:bg-red-50 disabled:opacity-50"
                onClick={() => {
                  if (window.confirm('Delete this card and all uploaded statements?')) {
                    delCard.mutate()
                  }
                }}
              >
                Delete card
              </button>
            </div>
          </form>
          {save.isError ? (
            <p className="border-t border-zinc-100 px-4 pb-4 text-sm text-red-600">{String(save.error)}</p>
          ) : null}
        </div>
      )}
    </Panel>
  )
}

function EmiPlanFormFields({
  desc,
  setDesc,
  loanType,
  setLoanType,
  limitR,
  setLimitR,
  principalR,
  setPrincipalR,
  emiR,
  setEmiR,
  outstandingR,
  setOutstandingR,
  tenure,
  setTenure,
  paid,
  setPaid,
  creationDate,
  setCreationDate,
  finishDate,
  setFinishDate,
  active,
  setActive,
  notes,
  setNotes,
  idPrefix,
}: {
  desc: string
  setDesc: (v: string) => void
  loanType: string
  setLoanType: (v: string) => void
  limitR: string
  setLimitR: (v: string) => void
  principalR: string
  setPrincipalR: (v: string) => void
  emiR: string
  setEmiR: (v: string) => void
  outstandingR: string
  setOutstandingR: (v: string) => void
  tenure: string
  setTenure: (v: string) => void
  paid: string
  setPaid: (v: string) => void
  creationDate: string
  setCreationDate: (v: string) => void
  finishDate: string
  setFinishDate: (v: string) => void
  active: boolean
  setActive: (v: boolean) => void
  notes: string
  setNotes: (v: string) => void
  idPrefix: string
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs font-medium text-zinc-700">
          Description
          <input
            id={`${idPrefix}-desc`}
            className="mt-1 block min-w-[10rem] rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm"
            value={desc}
            onChange={(ev) => setDesc(ev.target.value)}
            placeholder="e.g. Laptop — Amazon"
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          Transaction / loan type
          <input
            id={`${idPrefix}-loan`}
            className="mt-1 block min-w-[12rem] rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm"
            value={loanType}
            onChange={(ev) => setLoanType(ev.target.value)}
            placeholder="e.g. Merchant EMI conversions"
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          Limit blocked (₹)
          <input
            id={`${idPrefix}-limit`}
            className="mt-1 block w-28 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={limitR}
            onChange={(ev) => setLimitR(ev.target.value)}
            placeholder="60000"
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          EMI / loan amount (₹)
          <input
            id={`${idPrefix}-principal`}
            className="mt-1 block w-28 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={principalR}
            onChange={(ev) => setPrincipalR(ev.target.value)}
            placeholder="51349"
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          Monthly EMI (₹)
          <input
            id={`${idPrefix}-emi`}
            className="mt-1 block w-28 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={emiR}
            onChange={(ev) => setEmiR(ev.target.value)}
            placeholder="5000"
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          Outstanding instalments (₹)
          <input
            id={`${idPrefix}-out`}
            className="mt-1 block w-32 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={outstandingR}
            onChange={(ev) => setOutstandingR(ev.target.value)}
            placeholder="from statement"
          />
        </label>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs font-medium text-zinc-700">
          No. of installments
          <input
            id={`${idPrefix}-tenure`}
            className="mt-1 block w-20 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm tabular-nums"
            inputMode="numeric"
            value={tenure}
            onChange={(ev) => setTenure(ev.target.value)}
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          Installments paid
          <input
            id={`${idPrefix}-paid`}
            className="mt-1 block w-16 rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm tabular-nums"
            inputMode="numeric"
            value={paid}
            onChange={(ev) => setPaid(ev.target.value)}
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          Creation date
          <input
            id={`${idPrefix}-cdate`}
            type="date"
            className="mt-1 block rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm"
            value={creationDate}
            onChange={(ev) => setCreationDate(ev.target.value)}
          />
        </label>
        <label className="text-xs font-medium text-zinc-700">
          Finish date
          <input
            id={`${idPrefix}-fdate`}
            type="date"
            className="mt-1 block rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm"
            value={finishDate}
            onChange={(ev) => setFinishDate(ev.target.value)}
          />
        </label>
        <label className="flex flex-col text-xs font-medium text-zinc-700">
          <span>Active</span>
          <input
            type="checkbox"
            className="mt-2 h-4 w-4 rounded border-zinc-300 text-emerald-700"
            checked={active}
            onChange={(ev) => setActive(ev.target.checked)}
          />
        </label>
        <label className="min-w-[8rem] flex-1 text-xs font-medium text-zinc-700">
          Notes
          <input
            id={`${idPrefix}-notes`}
            className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-2 py-1.5 text-sm"
            value={notes}
            onChange={(ev) => setNotes(ev.target.value)}
          />
        </label>
      </div>
    </div>
  )
}

function CreditCardEmiBlock({
  cardId,
  emis,
  emisError,
  queryClient,
}: {
  cardId: number
  emis: CreditCardEmiOut[]
  emisError: unknown | null
  queryClient: QueryClient
}) {
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['credit-card-emis', cardId] })
    void queryClient.invalidateQueries({ queryKey: ['credit-card', cardId] })
    void queryClient.invalidateQueries({ queryKey: ['credit-cards'] })
  }

  const [desc, setDesc] = useState('')
  const [loanType, setLoanType] = useState('')
  const [limitR, setLimitR] = useState('')
  const [principalR, setPrincipalR] = useState('')
  const [emiR, setEmiR] = useState('')
  const [outstandingR, setOutstandingR] = useState('')
  const [tenure, setTenure] = useState('12')
  const [paid, setPaid] = useState('0')
  const [creationDate, setCreationDate] = useState('')
  const [finishDate, setFinishDate] = useState('')
  const [active, setActive] = useState(true)
  const [notes, setNotes] = useState('')

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editDesc, setEditDesc] = useState('')
  const [editLoanType, setEditLoanType] = useState('')
  const [editLimitR, setEditLimitR] = useState('')
  const [editPrincipalR, setEditPrincipalR] = useState('')
  const [editEmiR, setEditEmiR] = useState('')
  const [editOutstandingR, setEditOutstandingR] = useState('')
  const [editTenure, setEditTenure] = useState('')
  const [editPaid, setEditPaid] = useState('')
  const [editCreationDate, setEditCreationDate] = useState('')
  const [editFinishDate, setEditFinishDate] = useState('')
  const [editActive, setEditActive] = useState(true)
  const [editNotes, setEditNotes] = useState('')
  const [scheduleEstimatesOpen, setScheduleEstimatesOpen] = useState<Record<number, boolean>>({})
  const [emiDetailsExpanded, setEmiDetailsExpanded] = useState<Record<number, boolean>>({})

  const startEdit = (e: CreditCardEmiOut) => {
    setEditingId(e.id)
    setEditDesc(e.description)
    setEditLoanType(e.loan_type ?? '')
    setEditLimitR(String(e.limit_blocked_paise / 100))
    setEditPrincipalR(e.principal_paise != null ? String(e.principal_paise / 100) : '')
    setEditEmiR(String(e.emi_amount_paise / 100))
    setEditOutstandingR(
      e.outstanding_instalment_paise != null ? String(e.outstanding_instalment_paise / 100) : '',
    )
    setEditTenure(String(e.tenure_months))
    setEditPaid(String(e.installments_paid))
    setEditCreationDate(e.creation_date ?? '')
    setEditFinishDate(e.finish_date ?? '')
    setEditActive(e.is_active)
    setEditNotes(e.notes ?? '')
  }

  const cancelEdit = () => {
    setEditingId(null)
  }

  const buildEmiPayload = (opts: {
    desc: string
    loanType: string
    limitR: string
    principalR: string
    emiR: string
    outstandingR: string
    tenure: string
    paid: string
    creationDate: string
    finishDate: string
    active: boolean
    notes: string
  }) => {
    const lb = rupeesToPaise(opts.limitR)
    const em = rupeesToPaise(opts.emiR)
    const t = Number.parseInt(opts.tenure, 10)
    const p = Number.parseInt(opts.paid, 10)
    if (!opts.desc.trim() || lb == null || em == null || Number.isNaN(t) || t < 1 || Number.isNaN(p) || p < 0) {
      throw new Error('Enter description, limit blocked, monthly EMI, tenure (≥1), and installments paid.')
    }
    const pr = optionalRupeesField(opts.principalR)
    const os = optionalRupeesField(opts.outstandingR)
    if (opts.principalR.trim() && pr == null) {
      throw new Error('Check EMI / loan amount (principal).')
    }
    if (opts.outstandingR.trim() && os == null) {
      throw new Error('Check outstanding instalment amount.')
    }
    return {
      description: opts.desc.trim(),
      limit_blocked_paise: lb,
      emi_amount_paise: em,
      tenure_months: t,
      installments_paid: p,
      is_active: opts.active,
      notes: opts.notes.trim() || null,
      loan_type: opts.loanType.trim() || null,
      creation_date: opts.creationDate.trim() || null,
      finish_date: opts.finishDate.trim() || null,
      principal_paise: pr,
      outstanding_instalment_paise: os,
    }
  }

  const create = useMutation({
    mutationFn: () =>
      postCreditCardEmi(
        cardId,
        buildEmiPayload({
          desc,
          loanType,
          limitR,
          principalR,
          emiR,
          outstandingR,
          tenure,
          paid,
          creationDate,
          finishDate,
          active,
          notes,
        }),
      ),
    onSuccess: () => {
      invalidate()
      setDesc('')
      setLoanType('')
      setLimitR('')
      setPrincipalR('')
      setEmiR('')
      setOutstandingR('')
      setTenure('12')
      setPaid('0')
      setCreationDate('')
      setFinishDate('')
      setActive(true)
      setNotes('')
    },
  })

  const saveEdit = useMutation({
    mutationFn: (id: number) =>
      putCreditCardEmi(
        cardId,
        id,
        buildEmiPayload({
          desc: editDesc,
          loanType: editLoanType,
          limitR: editLimitR,
          principalR: editPrincipalR,
          emiR: editEmiR,
          outstandingR: editOutstandingR,
          tenure: editTenure,
          paid: editPaid,
          creationDate: editCreationDate,
          finishDate: editFinishDate,
          active: editActive,
          notes: editNotes,
        }),
      ),
    onSuccess: () => {
      invalidate()
      cancelEdit()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => deleteCreditCardEmi(cardId, id),
    onSuccess: () => {
      invalidate()
      cancelEdit()
    },
  })

  const [toDebtSuccessId, setToDebtSuccessId] = useState<number | null>(null)

  const toDebt = useMutation({
    mutationFn: (emiId: number) => convertEmiToDebt(cardId, emiId),
    onSuccess: (_debt, emiId) => {
      void queryClient.invalidateQueries({ queryKey: ['debt-list'] })
      setToDebtSuccessId(emiId)
    },
  })

  return (
    <Panel variant="emerald">
      <p className="mb-4 text-xs text-zinc-600">
        Match your statement’s <strong>EMI / personal loan on credit cards</strong> section: transaction type,
        dates, principal (EMI/loan amount), monthly EMI, tenure, paid vs pending, and outstanding instalment
        amount. <strong>Limit blocked</strong> is credit tied up; interest estimates use monthly EMI × tenure minus
        principal (principal defaults to limit blocked if you leave EMI/loan amount empty).
      </p>
      {emisError ? <p className="mb-2 text-sm text-red-600">{String(emisError)}</p> : null}

      <form
        className="mb-6 flex flex-col gap-3 rounded-xl border border-emerald-100 bg-emerald-50/40 p-4"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <p className="text-xs font-semibold uppercase tracking-wide text-emerald-900">Add EMI plan</p>
        <EmiPlanFormFields
          idPrefix="add-emi"
          desc={desc}
          setDesc={setDesc}
          loanType={loanType}
          setLoanType={setLoanType}
          limitR={limitR}
          setLimitR={setLimitR}
          principalR={principalR}
          setPrincipalR={setPrincipalR}
          emiR={emiR}
          setEmiR={setEmiR}
          outstandingR={outstandingR}
          setOutstandingR={setOutstandingR}
          tenure={tenure}
          setTenure={setTenure}
          paid={paid}
          setPaid={setPaid}
          creationDate={creationDate}
          setCreationDate={setCreationDate}
          finishDate={finishDate}
          setFinishDate={setFinishDate}
          active={active}
          setActive={setActive}
          notes={notes}
          setNotes={setNotes}
        />
        <div>
          <button
            type="submit"
            disabled={create.isPending}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            Add plan
          </button>
        </div>
        {create.isError ? <p className="text-sm text-red-600">{String(create.error)}</p> : null}
      </form>

      {emis.length === 0 ? (
        <p className="text-sm text-zinc-500">No EMI plans yet — add one above.</p>
      ) : (
        <ul className="space-y-2">
          {emis.map((e) => {
            const estimatesOpen = scheduleEstimatesOpen[e.id] ?? false
            const estimatesTriggerId = `emi-estimates-trigger-${e.id}`
            const estimatesPanelId = `emi-estimates-panel-${e.id}`
            const detailsOpen = emiDetailsExpanded[e.id] ?? false
            const detailsTriggerId = `emi-details-trigger-${e.id}`
            const detailsPanelId = `emi-details-panel-${e.id}`
            return (
            <li
              key={e.id}
              className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm"
            >
              {editingId === e.id ? (
                <div className="space-y-3 bg-amber-50/50 p-4">
                  <EmiPlanFormFields
                    idPrefix={`edit-emi-${e.id}`}
                    desc={editDesc}
                    setDesc={setEditDesc}
                    loanType={editLoanType}
                    setLoanType={setEditLoanType}
                    limitR={editLimitR}
                    setLimitR={setEditLimitR}
                    principalR={editPrincipalR}
                    setPrincipalR={setEditPrincipalR}
                    emiR={editEmiR}
                    setEmiR={setEditEmiR}
                    outstandingR={editOutstandingR}
                    setOutstandingR={setEditOutstandingR}
                    tenure={editTenure}
                    setTenure={setEditTenure}
                    paid={editPaid}
                    setPaid={setEditPaid}
                    creationDate={editCreationDate}
                    setCreationDate={setEditCreationDate}
                    finishDate={editFinishDate}
                    setFinishDate={setEditFinishDate}
                    active={editActive}
                    setActive={setEditActive}
                    notes={editNotes}
                    setNotes={setEditNotes}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={saveEdit.isPending}
                      className="rounded bg-emerald-700 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                      onClick={() => saveEdit.mutate(e.id)}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="rounded border border-zinc-200 bg-white px-3 py-1.5 text-xs"
                      onClick={cancelEdit}
                    >
                      Cancel
                    </button>
                    {saveEdit.isError ? (
                      <span className="text-xs text-red-600">{String(saveEdit.error)}</span>
                    ) : null}
                  </div>
                </div>
              ) : (
                <div>
                  <div className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:gap-3 sm:px-4">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold leading-tight text-zinc-900">{e.description}</p>
                      {e.loan_type ? (
                        <p className="truncate text-xs text-zinc-500">{e.loan_type}</p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm sm:justify-end">
                      <span className="tabular-nums text-zinc-800">
                        <span className="text-xs font-medium text-zinc-500">EMI </span>
                        {formatPaiseCompact(e.emi_amount_paise)}
                        <span className="text-zinc-500">/mo</span>
                      </span>
                      <span className="tabular-nums text-zinc-800">
                        <span className="text-xs font-medium text-zinc-500">Principal </span>
                        {formatPaiseCompact(e.principal_basis_paise)}
                      </span>
                      <span className="tabular-nums text-zinc-800">
                        <span className="text-xs font-medium text-zinc-500">Pending </span>
                        {e.pending_installments}
                      </span>
                      <span className="tabular-nums text-zinc-700">
                        <span className="text-xs font-medium text-zinc-500">Limit </span>
                        {formatPaiseCompact(e.limit_blocked_paise)}
                      </span>
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-zinc-100 pt-2 sm:border-t-0 sm:pt-0">
                      <button
                        type="button"
                        id={detailsTriggerId}
                        className="rounded-md border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium text-zinc-800 hover:bg-zinc-100"
                        aria-expanded={detailsOpen}
                        aria-controls={detailsPanelId}
                        onClick={() =>
                          setEmiDetailsExpanded((prev) => ({
                            ...prev,
                            [e.id]: !prev[e.id],
                          }))
                        }
                      >
                        {detailsOpen ? 'Less' : 'Details'}
                      </button>
                      {toDebtSuccessId === e.id ? (
                        <Link
                          to="/debt"
                          className="text-xs font-medium text-indigo-700 hover:underline"
                        >
                          View in Debts →
                        </Link>
                      ) : (
                        <button
                          type="button"
                          disabled={toDebt.isPending}
                          title="Create a Debt entry from this EMI plan"
                          className="text-xs font-medium text-indigo-700 hover:underline disabled:opacity-50"
                          onClick={() => {
                            if (window.confirm('Track this EMI as a Debt entry?')) {
                              toDebt.mutate(e.id)
                            }
                          }}
                        >
                          Track in Debts
                        </button>
                      )}
                      <button
                        type="button"
                        className="text-xs font-medium text-emerald-800 hover:underline"
                        onClick={() => startEdit(e)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        disabled={remove.isPending}
                        className="text-xs font-medium text-red-700 hover:underline disabled:opacity-50"
                        onClick={() => {
                          if (window.confirm('Remove this EMI plan?')) {
                            remove.mutate(e.id)
                          }
                        }}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                  {detailsOpen ? (
                    <div
                      id={detailsPanelId}
                      role="region"
                      aria-labelledby={detailsTriggerId}
                      className="border-t border-zinc-100 bg-zinc-50/40 px-3 py-3 sm:px-4"
                    >
                      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Creation date</dt>
                          <dd className="tabular-nums text-zinc-900">{formatOptionalIsoDate(e.creation_date)}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Finish date</dt>
                          <dd className="tabular-nums text-zinc-900">{formatOptionalIsoDate(e.finish_date)}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">No. of installments</dt>
                          <dd className="tabular-nums text-zinc-900">{e.tenure_months}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Monthly EMI</dt>
                          <dd className="tabular-nums text-zinc-900">{formatPaiseCompact(e.emi_amount_paise)}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">EMI / loan amount (principal)</dt>
                          <dd className="tabular-nums text-zinc-900">
                            {e.principal_paise != null ? formatPaiseCompact(e.principal_paise) : '—'}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Principal (basis for interest)</dt>
                          <dd className="tabular-nums text-zinc-900">{formatPaiseCompact(e.principal_basis_paise)}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Installments paid</dt>
                          <dd className="tabular-nums text-zinc-900">{e.installments_paid}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Pending installments</dt>
                          <dd className="tabular-nums text-zinc-900">{e.pending_installments}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Outstanding instalment amount</dt>
                          <dd className="tabular-nums text-zinc-900">
                            {e.outstanding_instalment_paise != null
                              ? formatPaiseCompact(e.outstanding_instalment_paise)
                              : '—'}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Limit blocked</dt>
                          <dd className="tabular-nums text-zinc-900">{formatPaiseCompact(e.limit_blocked_paise)}</dd>
                        </div>
                        <div className="flex justify-between gap-4 sm:block">
                          <dt className="text-xs font-medium text-zinc-500">Active</dt>
                          <dd className="text-zinc-900">{e.is_active ? 'Yes' : 'No'}</dd>
                        </div>
                        {e.notes ? (
                          <div className="sm:col-span-2">
                            <dt className="text-xs font-medium text-zinc-500">Notes</dt>
                            <dd className="text-zinc-800">{e.notes}</dd>
                          </div>
                        ) : null}
                      </dl>
                      <button
                        type="button"
                        id={estimatesTriggerId}
                        aria-expanded={estimatesOpen}
                        aria-controls={estimatesPanelId}
                        className="mt-4 flex w-full items-center justify-between gap-2 rounded-lg border border-emerald-200/80 bg-emerald-50/40 px-3 py-2 text-left text-xs font-medium text-emerald-950 hover:bg-emerald-50"
                        onClick={() =>
                          setScheduleEstimatesOpen((prev) => ({
                            ...prev,
                            [e.id]: !prev[e.id],
                          }))
                        }
                      >
                        <span className="font-semibold uppercase tracking-wide">Schedule estimates</span>
                        <span className="shrink-0 text-zinc-600">{estimatesOpen ? 'Hide' : 'Show'}</span>
                      </button>
                      {estimatesOpen ? (
                        <div
                          id={estimatesPanelId}
                          role="region"
                          aria-labelledby={estimatesTriggerId}
                          className="mt-2 rounded-lg border border-emerald-100 bg-emerald-50/50 p-3"
                        >
                          <p className="mb-2 text-xs text-zinc-600">
                            Total repayment = monthly EMI × tenure. Total interest = that sum minus principal basis.
                            Interest paid / remaining split assumes interest accrues evenly across tenure
                            (approximation).
                          </p>
                          <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                            <div className="flex justify-between gap-4 sm:block">
                              <dt className="text-xs font-medium text-zinc-500">Total repayment (schedule)</dt>
                              <dd className="tabular-nums font-medium text-zinc-900">
                                {formatPaiseCompact(e.total_repayment_schedule_paise)}
                              </dd>
                            </div>
                            <div className="flex justify-between gap-4 sm:block">
                              <dt className="text-xs font-medium text-zinc-500">Total interest (estimate)</dt>
                              <dd className="tabular-nums font-medium text-zinc-900">
                                {formatPaiseCompact(e.total_interest_estimated_paise)}
                              </dd>
                            </div>
                            <div className="flex justify-between gap-4 sm:block">
                              <dt className="text-xs font-medium text-zinc-500">Interest % on principal</dt>
                              <dd className="tabular-nums font-medium text-zinc-900">
                                {e.interest_over_principal_pct != null
                                  ? `${e.interest_over_principal_pct.toFixed(2)}%`
                                  : '—'}
                              </dd>
                            </div>
                            <div className="flex justify-between gap-4 sm:block">
                              <dt className="text-xs font-medium text-zinc-500">Amount paid to date</dt>
                              <dd className="tabular-nums text-zinc-900">
                                {formatPaiseCompact(e.amount_paid_to_date_paise)}
                              </dd>
                            </div>
                            <div className="flex justify-between gap-4 sm:block">
                              <dt className="text-xs font-medium text-zinc-500">Interest paid (est.)</dt>
                              <dd className="tabular-nums text-zinc-900">
                                {formatPaiseCompact(e.interest_paid_estimated_paise)}
                              </dd>
                            </div>
                            <div className="flex justify-between gap-4 sm:block">
                              <dt className="text-xs font-medium text-zinc-500">Interest remaining (est.)</dt>
                              <dd className="tabular-nums text-zinc-900">
                                {formatPaiseCompact(e.interest_remaining_estimated_paise)}
                              </dd>
                            </div>
                          </dl>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              )}
            </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}

const INTEREST_KEYWORDS = ['interest', 'finance charge', 'late fee', 'cash advance', 'annual fee', 'gst on interest', 'overlimit', 'over limit', 'penalty']

function isInterestOrFee(tx: TransactionRow): boolean {
  const hay = `${tx.merchant ?? ''} ${tx.category ?? ''}`.toLowerCase()
  return INTEREST_KEYWORDS.some((k) => hay.includes(k))
}

function getBillingCycleLabel(dateStr: string, statementDay: number): string {
  const d = new Date(`${dateStr}T12:00:00`)
  const day = d.getDate()
  const cycleStart =
    day >= statementDay
      ? new Date(d.getFullYear(), d.getMonth(), statementDay)
      : new Date(d.getFullYear(), d.getMonth() - 1, statementDay)
  const cycleEnd = new Date(cycleStart.getFullYear(), cycleStart.getMonth() + 1, statementDay - 1)
  const fmt = (x: Date) => x.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
  return `${fmt(cycleStart)} – ${fmt(cycleEnd)}`
}

function getMonthLabel(dateStr: string): string {
  const d = new Date(`${dateStr}T12:00:00`)
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

function groupTransactions(
  txs: TransactionRow[],
  statementDay: number | null,
): Array<{ label: string; txs: TransactionRow[]; debitTotal: number; creditTotal: number }> {
  const map = new Map<string, TransactionRow[]>()
  for (const tx of txs) {
    if (!tx.date) continue
    const label = statementDay ? getBillingCycleLabel(tx.date, statementDay) : getMonthLabel(tx.date)
    const arr = map.get(label) ?? []
    arr.push(tx)
    map.set(label, arr)
  }
  return Array.from(map.entries()).map(([label, list]) => ({
    label,
    txs: list,
    debitTotal: list.filter((t) => t.transaction_type === 'debit').reduce((s, t) => s + t.amount_paise, 0),
    creditTotal: list.filter((t) => t.transaction_type === 'credit').reduce((s, t) => s + t.amount_paise, 0),
  }))
}

function CcInsightsPanel({
  accountId,
  rewardRatePct,
}: {
  accountId: number
  rewardRatePct: number | null
}) {
  const txQ = useQuery({
    queryKey: ['cc-transactions', accountId],
    queryFn: () => fetchTransactions(500, { accountId }),
    staleTime: 60_000,
  })

  if (txQ.isPending || !txQ.data) return null

  const debits = txQ.data.filter((t) => t.transaction_type === 'debit')

  // Build last-6-calendar-months spend buckets
  const now = new Date()
  const buckets: { label: string; key: string; spent_paise: number }[] = []
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
    buckets.push({ key, label, spent_paise: 0 })
  }
  for (const t of debits) {
    const key = t.date.slice(0, 7)
    const b = buckets.find((x) => x.key === key)
    if (b) b.spent_paise += t.amount_paise
  }

  const totalSpend = debits.reduce((s, t) => s + t.amount_paise, 0)
  const estimatedRewards =
    rewardRatePct != null && rewardRatePct > 0
      ? Math.round(totalSpend * (rewardRatePct / 100))
      : null

  const chartData = buckets.map((b) => ({
    label: b.label,
    spent_rupees: b.spent_paise / 100,
  }))

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Monthly spend — last 6 months
        </p>
        <ResponsiveContainer width="100%" height={180} minWidth={0}>
          <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
            <XAxis dataKey="label" tick={{ fontSize: 11 }} />
            <YAxis
              tick={{ fontSize: 10 }}
              tickFormatter={(v: number) => formatPaiseCompact(Math.round(v * 100))}
              width={56}
            />
            <Tooltip
              formatter={(v) => [formatPaiseCompact(Math.round(Number(v ?? 0) * 100)), 'Spent']}
            />
            <Bar dataKey="spent_rupees" fill="#0f766e" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {estimatedRewards != null ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-700">
            Reward optimisation
          </p>
          <p className="text-sm text-zinc-700">
            At <span className="font-semibold">{rewardRatePct}%</span> reward rate, your{' '}
            <span className="font-semibold tabular-nums">{formatPaiseCompact(totalSpend)}</span> total
            spend has earned approximately{' '}
            <span className="font-semibold tabular-nums text-emerald-800">
              {formatPaiseCompact(estimatedRewards)}
            </span>{' '}
            in rewards.
          </p>
        </div>
      ) : (
        <p className="text-xs text-zinc-400">
          Set a reward rate % on this card to see estimated cashback / points value.
        </p>
      )}
    </div>
  )
}

function CcTransactionList({
  accountId,
  statementDay,
  cardName,
}: {
  accountId: number
  statementDay: number | null
  cardName: string
}) {
  const txQ = useQuery({
    queryKey: ['cc-transactions', accountId],
    queryFn: () => fetchTransactions(500, { accountId }),
    staleTime: 60_000,
  })

  if (txQ.isPending) return <Panel className="text-sm text-zinc-500 py-6 text-center">Loading transactions…</Panel>
  if (txQ.isError) return <p className="text-sm text-red-600">{String(txQ.error)}</p>

  const txs = (txQ.data ?? []).filter((t) => t.transaction_type !== 'transfer')
  if (txs.length === 0) {
    return (
      <Panel className="text-sm text-zinc-500 py-6 text-center">
        No transactions yet — import a statement or log spending on <em>{cardName}</em>.
      </Panel>
    )
  }

  const groups = groupTransactions(txs, statementDay)

  return (
    <div className="space-y-4">
      {groups.map((g) => {
        const interestTotal = g.txs
          .filter((t) => isInterestOrFee(t) && t.transaction_type === 'debit')
          .reduce((s, t) => s + t.amount_paise, 0)
        return (
          <Panel key={g.label} padding={false} className="overflow-hidden">
            {/* Cycle header */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 bg-zinc-50/60 px-4 py-2.5">
              <span className="text-sm font-semibold text-zinc-800">{g.label}</span>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs tabular-nums">
                <span className="text-zinc-600">
                  <span className="font-medium text-zinc-500">Spent </span>
                  {formatPaiseCompact(g.debitTotal)}
                </span>
                {g.creditTotal > 0 ? (
                  <span className="text-emerald-700">
                    <span className="font-medium">Credits </span>
                    {formatPaiseCompact(g.creditTotal)}
                  </span>
                ) : null}
                {interestTotal > 0 ? (
                  <span className="font-medium text-red-700">
                    Interest/fees {formatPaiseCompact(interestTotal)}
                  </span>
                ) : null}
                <span className="text-zinc-400">{g.txs.length} txn{g.txs.length !== 1 ? 's' : ''}</span>
              </div>
            </div>
            {/* Transaction rows */}
            <ul className="divide-y divide-zinc-50">
              {g.txs.map((tx) => {
                const warn = isInterestOrFee(tx) && tx.transaction_type === 'debit'
                return (
                  <li
                    key={tx.id}
                    className={`flex items-center gap-3 px-4 py-2.5 text-sm ${warn ? 'bg-red-50/40' : ''}`}
                  >
                    <span className="w-20 shrink-0 text-xs tabular-nums text-zinc-400">{tx.date}</span>
                    <span className="min-w-0 flex-1 truncate">
                      <span className={`font-medium ${warn ? 'text-red-800' : 'text-zinc-900'}`}>
                        {tx.merchant || '—'}
                      </span>
                      {tx.category ? (
                        <span className="ml-2 text-xs text-zinc-400">{tx.category}</span>
                      ) : null}
                      {warn ? <span className="ml-2 text-xs font-semibold text-red-600">⚠ interest/fee</span> : null}
                    </span>
                    <span
                      className={`shrink-0 tabular-nums font-medium ${
                        tx.transaction_type === 'credit' ? 'text-emerald-700' : 'text-zinc-900'
                      }`}
                    >
                      {tx.transaction_type === 'credit' ? '+' : ''}
                      {formatPaiseCompact(tx.amount_paise)}
                    </span>
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                        tx.transaction_type === 'credit'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-zinc-100 text-zinc-700'
                      }`}
                    >
                      {tx.transaction_type === 'credit' ? 'CR' : 'DR'}
                    </span>
                  </li>
                )
              })}
            </ul>
          </Panel>
        )
      })}
      <p className="text-center text-xs text-zinc-400">
        Showing last 500 transactions · Transfers (bill payments) excluded ·{' '}
        <Link to="/transactions" className="text-emerald-700 hover:underline">
          View all in Transactions →
        </Link>
      </p>
    </div>
  )
}

function PayBillDrawer({
  cardId,
  cardName,
  accounts,
  onClose,
  queryClient,
}: {
  cardId: number
  cardName: string
  accounts: AccountOut[]
  onClose: () => void
  queryClient: QueryClient
}) {
  const today = new Date().toISOString().slice(0, 10)
  const [fromAccountId, setFromAccountId] = useState('')
  const [amountR, setAmountR] = useState('')
  const [date, setDate] = useState(today)
  const [notes, setNotes] = useState('')

  const payable = accounts.filter((a) => a.type !== 'credit_card' && a.is_active)

  const pay = useMutation({
    mutationFn: () => {
      const aid = Number.parseInt(fromAccountId, 10)
      if (!aid) throw new Error('Select a bank account')
      const amount = rupeesToPaise(amountR)
      if (amount == null || amount <= 0) throw new Error('Enter a valid amount')
      return payCcBill(cardId, { from_account_id: aid, amount_paise: amount, date, notes: notes.trim() || null })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['credit-card', cardId] })
      void queryClient.invalidateQueries({ queryKey: ['cc-live-balance', cardId] })
      void queryClient.invalidateQueries({ queryKey: ['transactions'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void queryClient.invalidateQueries({ queryKey: ['net-worth'] })
      onClose()
    },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-end sm:items-start" role="dialog" aria-modal>
      <button type="button" className="absolute inset-0 bg-black/30" onClick={onClose} aria-label="Close" />
      <div className="relative z-10 w-full max-w-md rounded-t-2xl bg-white shadow-2xl sm:mt-16 sm:mr-6 sm:rounded-2xl">
        <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-4">
          <h2 className="text-base font-semibold text-zinc-900">Pay bill — {cardName}</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-zinc-500 hover:bg-zinc-100">✕</button>
        </div>
        <form
          className="flex flex-col gap-4 p-5"
          onSubmit={(e) => { e.preventDefault(); pay.mutate() }}
        >
          <label className="text-xs font-medium text-zinc-700">
            Pay from account
            <select
              className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"
              value={fromAccountId}
              onChange={(e) => setFromAccountId(e.target.value)}
              required
            >
              <option value="">Select account…</option>
              {payable.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}{a.institution ? ` · ${a.institution}` : ''}
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-xs font-medium text-zinc-700">
              Amount (₹)
              <input
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={amountR}
                onChange={(e) => setAmountR(e.target.value)}
                placeholder="0.00"
                required
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Date
              <input
                type="date"
                className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </label>
          </div>
          <label className="text-xs font-medium text-zinc-700">
            Notes (optional)
            <input
              className="mt-1 block w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={`CC bill payment · ${cardName}`}
            />
          </label>
          {pay.isError ? (
            <p className="text-sm text-red-600">{String(pay.error)}</p>
          ) : null}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={pay.isPending}
              className="flex-1 rounded-lg bg-emerald-700 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {pay.isPending ? 'Recording…' : 'Record payment'}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-200 px-4 py-2.5 text-sm text-zinc-700 hover:bg-zinc-50"
            >
              Cancel
            </button>
          </div>
          <p className="text-xs text-zinc-500">
            Records as a transfer from the selected account to the CC linked account. Shows in Transactions as a transfer (excluded from spend totals).
          </p>
        </form>
      </div>
    </div>
  )
}

export function CreditCardDetailPage() {
  const { cardId: cardIdParam } = useParams<{ cardId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const cardId = Number.parseInt(cardIdParam ?? '', 10)

  const [payBillOpen, setPayBillOpen] = useState(false)

  const card = useQuery({
    queryKey: ['credit-card', cardId],
    queryFn: () => fetchCreditCard(cardId),
    enabled: Number.isFinite(cardId) && cardId > 0,
  })

  const liveBalance = useQuery({
    queryKey: ['cc-live-balance', cardId],
    queryFn: () => fetchCcLiveBalance(cardId),
    enabled: Number.isFinite(cardId) && cardId > 0 && (card.data?.account_id ?? 0) > 0,
  })

  const leakage = useQuery({
    queryKey: ['cc-interest-leakage', cardId],
    queryFn: () => fetchCcInterestLeakage(cardId),
    enabled: Number.isFinite(cardId) && cardId > 0 && (card.data?.account_id ?? 0) > 0,
    staleTime: 5 * 60_000,
  })

  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: () => fetchAccounts(),
  })

  const statements = useQuery({
    queryKey: ['credit-card-statements', cardId],
    queryFn: () => fetchCreditCardStatements(cardId),
    enabled: Number.isFinite(cardId) && cardId > 0,
  })

  const emis = useQuery({
    queryKey: ['credit-card-emis', cardId],
    queryFn: () => fetchCreditCardEmis(cardId),
    enabled: Number.isFinite(cardId) && cardId > 0,
  })

  const [pdfPass, setPdfPass] = useState('')

  const upload = useMutation({
    mutationKey: ['file-upload'],
    mutationFn: (file: File) => uploadCreditCardStatement(cardId, file, pdfPass || undefined),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['credit-card-statements', cardId] })
      setPdfPass('')
    },
  })

  if (!Number.isFinite(cardId) || cardId <= 0) {
    return <PageError title="Invalid card" message={<p className="text-sm">Check the URL.</p>} />
  }

  if (card.isPending || statements.isPending) {
    return <PageLoading lines={3} showFooterBlock />
  }

  if (card.isError || !card.data) {
    return (
      <PageError
        title="Card not found"
        message={
          <p className="text-sm">
            {String(card.error ?? '')}{' '}
            <Link to="/credit-cards" className="text-emerald-800 underline">
              Back to cards
            </Link>
          </p>
        }
      />
    )
  }

  const c = card.data
  const util = c.utilization_pct
  const emiBlocked = c.emi_limit_blocked_paise ?? 0
  const emiMonthly = c.emi_monthly_due_paise ?? 0
  const totalUsed = c.total_limit_used_paise ?? (c.current_balance_paise ?? 0) + emiBlocked
  const liveBal = liveBalance.data?.live_balance_paise ?? null
  const hasLinkedAccount = (c.account_id ?? 0) > 0

  return (
    <div className="space-y-10">
      {payBillOpen ? (
        <PayBillDrawer
          cardId={cardId}
          cardName={c.name}
          accounts={accounts.data ?? []}
          onClose={() => setPayBillOpen(false)}
          queryClient={qc}
        />
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link
            to="/credit-cards"
            className="text-xs font-medium text-emerald-700 hover:underline"
          >
            ← All credit cards
          </Link>
          <PageHero
            eyebrow="Credit card"
            title={c.name}
            description={
              <>
                {c.issuer ? `${c.issuer} · ` : null}
                {c.last_four ? `···${c.last_four}` : 'Manage limit, utilisation, and statement imports.'}
              </>
            }
          />
        </div>
        <button
          type="button"
          onClick={() => setPayBillOpen(true)}
          className="shrink-0 rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800"
        >
          Pay bill
        </button>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <KpiCard tone="neutral" label="Credit limit" value={formatPaiseCompact(c.credit_limit_paise)} />
        <KpiCard
          tone="balance"
          label="Live balance"
          value={
            liveBalance.isPending && hasLinkedAccount
              ? '…'
              : liveBal != null
                ? formatPaiseCompact(liveBal)
                : '—'
          }
          hint={hasLinkedAccount ? 'From transaction history on linked account' : 'No linked account yet'}
        />
        <KpiCard
          tone="balance"
          label="Statement balance"
          value={c.current_balance_paise != null ? formatPaiseCompact(c.current_balance_paise) : '—'}
          hint="Last updated from statement import"
        />
        <KpiCard
          tone="neutral"
          label="EMI limit blocked"
          value={emiBlocked > 0 ? formatPaiseCompact(emiBlocked) : '—'}
          hint="Limit held by active EMIs"
        />
        <KpiCard tone="spending" label="Total limit used" value={formatPaiseCompact(totalUsed)} />
        <KpiCard
          tone="neutral"
          label="EMI due / month"
          value={emiMonthly > 0 ? formatPaiseCompact(emiMonthly) : '—'}
          hint="Sum of monthly EMI for active plans"
        />
        <KpiCard
          tone="spending"
          label="Utilisation"
          value={util != null ? `${util.toFixed(1)}%` : '—'}
          hint={c.credit_limit_paise > 0 ? 'Total used ÷ limit' : undefined}
        />
        {c.statement_day || c.due_day ? (
          <KpiCard
            tone="neutral"
            label="Billing cycle"
            value={c.statement_day && c.due_day ? `${c.statement_day}→${c.due_day}` : c.statement_day ? `Stmt ${c.statement_day}` : `Due ${c.due_day}`}
            hint={`Statement day ${c.statement_day ?? '?'} · Payment due day ${c.due_day ?? '?'}`}
          />
        ) : null}
        {c.reward_rate_pct != null ? (
          <KpiCard
            tone="neutral"
            label="Reward rate"
            value={`${c.reward_rate_pct}%`}
            hint="Per ₹100 spend"
          />
        ) : null}
        {hasLinkedAccount && leakage.data ? (
          <>
            <KpiCard
              tone="spending"
              label="Interest/fees this FY"
              value={leakage.data.fy_paise > 0 ? formatPaiseCompact(leakage.data.fy_paise) : '₹0'}
              hint="Interest charges + fees detected in transactions"
            />
            <KpiCard
              tone="spending"
              label="Interest/fees all-time"
              value={leakage.data.all_time_paise > 0 ? formatPaiseCompact(leakage.data.all_time_paise) : '₹0'}
              hint="Total leakage since first transaction"
            />
          </>
        ) : null}
      </section>

      {hasLinkedAccount && leakage.data && leakage.data.fy_paise > 0 ? (
        <div className="rounded-xl border border-red-200 bg-red-50/60 px-4 py-3 text-sm text-red-900">
          <span className="font-semibold">Interest leakage detected</span> — you've paid{' '}
          <span className="font-semibold tabular-nums">{formatPaiseCompact(leakage.data.fy_paise)}</span>{' '}
          in interest and fees on this card this financial year. Consider paying the full outstanding balance before the due date to avoid future charges.
        </div>
      ) : null}

      {util != null && c.credit_limit_paise > 0 ? (
        <div className="max-w-xl">
          <p className="mb-1 text-xs font-medium text-zinc-600">Utilisation bar</p>
          <div className="h-3 overflow-hidden rounded-full bg-zinc-100 ring-1 ring-inset ring-zinc-200/80">
            <div
              className={`h-full rounded-full transition-all ${
                util >= 90 ? 'bg-red-500' : util >= 70 ? 'bg-amber-500' : 'bg-emerald-600'
              }`}
              style={{ width: `${Math.min(100, util)}%` }}
            />
          </div>
        </div>
      ) : null}

      {hasLinkedAccount ? (
        <section>
          <SectionTitle>Insights</SectionTitle>
          <CcInsightsPanel
            accountId={c.account_id!}
            rewardRatePct={c.reward_rate_pct ?? null}
          />
        </section>
      ) : null}

      {hasLinkedAccount ? (
        <section>
          <SectionTitle>Transactions</SectionTitle>
          <CcTransactionList
            accountId={c.account_id!}
            statementDay={c.statement_day ?? null}
            cardName={c.name}
          />
        </section>
      ) : null}

      <section>
        <SectionTitle>EMI plans</SectionTitle>
        {emis.isPending ? (
          <Panel className="text-sm text-zinc-500">Loading EMI plans…</Panel>
        ) : (
          <CreditCardEmiBlock
            cardId={cardId}
            emis={emis.data ?? []}
            emisError={emis.isError ? emis.error : null}
            queryClient={qc}
          />
        )}
      </section>

      <section>
        <SectionTitle>Card details</SectionTitle>
        <CreditCardEditForm
          key={`${c.id}-${c.credit_limit_paise}-${c.current_balance_paise ?? 'n'}-${c.name}`}
          card={c}
          cardId={cardId}
          navigate={navigate}
          queryClient={qc}
        />
      </section>

      <section>
        <SectionTitle>Upload statement</SectionTitle>
        <Panel variant="emerald">
          <p className="mb-3 text-sm text-zinc-600">
            PDF (text extracted locally) or CSV / Excel with columns <strong>date</strong>,{' '}
            <strong>amount</strong>, <strong>category</strong> (and optional merchant). Parsed lines appear
            for review before you import them into Transactions.
          </p>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
            <label className="text-xs font-medium text-zinc-700">
              PDF password (if encrypted)
              <input
                type="password"
                className="mt-1 block h-10 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={pdfPass}
                onChange={(e) => setPdfPass(e.target.value)}
                autoComplete="off"
              />
            </label>
            <input
              type="file"
              accept=".pdf,.csv,.xlsx,.xlsm,application/pdf,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="text-sm text-zinc-700 file:mr-3 file:rounded-md file:border-0 file:bg-emerald-50 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-emerald-900 hover:file:bg-emerald-100"
              disabled={upload.isPending}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) {
                  upload.mutate(f)
                }
                e.target.value = ''
              }}
            />
            {upload.isPending ? <span className="text-sm text-zinc-500">Processing…</span> : null}
          </div>
          {upload.isPending ? (
            <p className="mt-3 text-xs text-zinc-500">
              A green bar at the top of the app shows progress. PDFs may call LM Studio for several minutes —
              keep this tab open. Increase <code className="rounded bg-zinc-100 px-1">LM_STUDIO_TIMEOUT_SECONDS</code>{' '}
              if requests time out.
            </p>
          ) : null}
          {upload.isError ? <p className="mt-2 text-sm text-red-600">{String(upload.error)}</p> : null}
        </Panel>
      </section>

      {!statements.isError && (statements.data ?? []).length > 0 ? (
        <section>
          <SectionTitle>Statement summary</SectionTitle>
          <CreditCardStatementSummarySection statements={statements.data ?? []} />
        </section>
      ) : null}

      <section>
        <SectionTitle>Statements</SectionTitle>
        {statements.isError ? (
          <p className="text-sm text-red-600">{String(statements.error)}</p>
        ) : null}
        {(statements.data ?? []).length === 0 ? (
          <Panel className="text-sm text-zinc-600">No statements uploaded yet.</Panel>
        ) : (
          <div className="space-y-3">
            {(statements.data ?? []).map((s) => {
              const lineTotal = s.line_items.reduce((sum, row) => {
                const ap = row.amount_paise
                return sum + (typeof ap === 'number' ? ap : 0)
              }, 0)
              return (
                <Panel key={s.id}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-zinc-900">{s.filename}</p>
                      <p className="mt-1 text-xs text-zinc-500">
                        {s.period_start && s.period_end
                          ? `${s.period_start} → ${s.period_end}`
                          : 'Period not detected'}
                        {s.created_at ? ` · ${s.created_at}` : ''}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 font-semibold ${
                            s.status === 'applied'
                              ? 'bg-emerald-100 text-emerald-900'
                              : 'bg-amber-100 text-amber-950'
                          }`}
                        >
                          {s.status}
                        </span>
                        {lineTotal > 0 ? (
                          <span className="tabular-nums text-zinc-600">
                            Parsed lines {formatPaiseCompact(lineTotal)}
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <Link
                      to={`/credit-cards/${cardId}/statements/${s.id}`}
                      className="shrink-0 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800"
                    >
                      Open statement
                    </Link>
                  </div>
                </Panel>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
