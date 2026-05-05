import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  deleteInsurancePolicy,
  deleteInsurancePremium,
  fetchInsurancePolicies,
  fetchInsurancePremiums,
  fetchInsuranceSummary,
  postInsurancePolicy,
  postInsurancePremium,
  putInsurancePolicy,
} from '@/lib/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'
import type { InsurancePolicyOut, InsurancePremiumOut } from '@/types/api'


const POLICY_TYPES = ['health', 'life', 'term', 'vehicle', 'home', 'travel', 'other'] as const
const PREMIUM_FREQUENCIES = ['annual', 'semi_annual', 'quarterly', 'monthly'] as const
const TAX_SECTIONS = ['80C', '80D', '80D_parents'] as const
const POLICY_STATUSES = ['active', 'lapsed', 'surrendered', 'matured'] as const

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) return null
  return Math.round(n * 100)
}

function paiseToRupees(p: number | null | undefined): string {
  if (p == null) return ''
  return String(p / 100)
}

function typeBadgeColor(type: string): string {
  switch (type) {
    case 'health': return 'bg-red-100 text-red-700'
    case 'life': return 'bg-blue-100 text-blue-700'
    case 'term': return 'bg-indigo-100 text-indigo-700'
    case 'vehicle': return 'bg-amber-100 text-amber-800'
    case 'home': return 'bg-emerald-100 text-emerald-800'
    case 'travel': return 'bg-cyan-100 text-cyan-700'
    default: return 'bg-zinc-100 text-zinc-700'
  }
}

function statusBadgeColor(status: string): string {
  switch (status) {
    case 'active': return 'bg-emerald-100 text-emerald-800'
    case 'lapsed': return 'bg-red-100 text-red-700'
    case 'surrendered': return 'bg-orange-100 text-orange-700'
    case 'matured': return 'bg-zinc-100 text-zinc-600'
    default: return 'bg-zinc-100 text-zinc-600'
  }
}

function taxBadgeColor(section: string | null): string {
  if (!section) return ''
  switch (section) {
    case '80C': return 'bg-violet-100 text-violet-700'
    case '80D': return 'bg-teal-100 text-teal-700'
    case '80D_parents': return 'bg-teal-50 text-teal-600'
    default: return 'bg-zinc-100 text-zinc-600'
  }
}

function isRenewalSoon(renewalDate: string | null): boolean {
  if (!renewalDate) return false
  const diffMs = new Date(renewalDate).getTime() - Date.now()
  const diffDays = diffMs / (1000 * 60 * 60 * 24)
  return diffDays >= 0 && diffDays <= 60
}

export function InsurancePage() {
  const qc = useQueryClient()
  const [showAddModal, setShowAddModal] = useState(false)
  const [editPolicy, setEditPolicy] = useState<InsurancePolicyOut | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const summary = useQuery({
    queryKey: ['insurance-summary'],
    queryFn: fetchInsuranceSummary,
  })

  const policies = useQuery({
    queryKey: ['insurance-policies'],
    queryFn: fetchInsurancePolicies,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['insurance-policies'] })
    void qc.invalidateQueries({ queryKey: ['insurance-summary'] })
  }

  const create = useMutation({
    mutationFn: postInsurancePolicy,
    onSuccess: () => {
      invalidate()
      setShowAddModal(false)
    },
  })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      putInsurancePolicy(id, body),
    onSuccess: () => {
      invalidate()
      setEditPolicy(null)
    },
  })

  const remove = useMutation({
    mutationFn: deleteInsurancePolicy,
    onSuccess: invalidate,
  })

  if (summary.isPending || policies.isPending) return <PageLoading lines={4} />
  if (summary.isError || policies.isError) {
    return (
      <PageError
        title="Could not load insurance data"
        message={<p className="text-sm">{String(summary.error ?? policies.error)}</p>}
      />
    )
  }

  const s = summary.data
  const list = policies.data

  // Group by policyholder — Self first, then others
  const grouped = list.reduce<Record<string, InsurancePolicyOut[]>>((acc, p) => {
    const key = p.policyholder || 'Unknown'
    if (!acc[key]) acc[key] = []
    acc[key].push(p)
    return acc
  }, {})
  const holderOrder = Object.keys(grouped).sort((a, b) => {
    if (a.toLowerCase() === 'self') return -1
    if (b.toLowerCase() === 'self') return 1
    return a.localeCompare(b)
  })

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Protection"
        title="Insurance"
        description="Health, life, vehicle & other policies · refreshes every 30s"
      />

      {/* KPI cards */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <KpiCard tone="neutral" label="Active policies" value={String(s.active_policy_count)} />
        <KpiCard tone="balance" label="Annual premium" value={formatPaiseCompact(s.total_annual_premium_paise)} />
        <KpiCard
          tone={s.renewing_within_60_days > 0 ? 'balance' : 'neutral'}
          label="Renewing in 60d"
          value={String(s.renewing_within_60_days)}
        />
        <KpiCard tone="neutral" label="80D (Self)" value={formatPaiseCompact(s.total_80d_self_paise)} />
        <KpiCard tone="neutral" label="80D (Parents)" value={formatPaiseCompact(s.total_80d_parents_paise)} />
        <KpiCard tone="neutral" label="80C deduction" value={formatPaiseCompact(s.total_80c_paise)} />
      </section>

      {/* Policy list */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <SectionTitle>Your policies</SectionTitle>
          <button
            type="button"
            onClick={() => setShowAddModal(true)}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800"
          >
            + Add policy
          </button>
        </div>

        {list.length === 0 ? (
          <Panel>
            <p className="py-6 text-center text-sm text-zinc-500">
              No insurance policies yet — add one to start tracking.
            </p>
          </Panel>
        ) : (
          <div className="space-y-6">
            {holderOrder.map((holder) => (
              <div key={holder}>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">{holder}</p>
                <div className="space-y-3">
                  {grouped[holder].map((policy) => (
                    <PolicyCard
                      key={policy.id}
                      policy={policy}
                      expanded={expandedId === policy.id}
                      onToggleExpand={() => setExpandedId(expandedId === policy.id ? null : policy.id)}
                      onEdit={() => setEditPolicy(policy)}
                      onDelete={() => {
                        if (window.confirm(`Delete policy "${policy.name}"?`)) {
                          remove.mutate(policy.id)
                        }
                      }}
                      invalidatePolicies={invalidate}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
        {remove.isError ? <p className="mt-2 text-sm text-red-600">{String(remove.error)}</p> : null}
      </section>

      {/* Add modal */}
      {showAddModal ? (
        <PolicyFormModal
          title="Add policy"
          initialData={null}
          onClose={() => setShowAddModal(false)}
          onSubmit={(body) => create.mutate(body)}
          isPending={create.isPending}
          error={create.isError ? String(create.error) : null}
        />
      ) : null}

      {/* Edit modal */}
      {editPolicy ? (
        <PolicyFormModal
          title="Edit policy"
          initialData={editPolicy}
          onClose={() => setEditPolicy(null)}
          onSubmit={(body) => update.mutate({ id: editPolicy.id, body })}
          isPending={update.isPending}
          error={update.isError ? String(update.error) : null}
        />
      ) : null}
    </div>
  )
}

// ── Policy card ──────────────────────────────────────────────────────────────

function PolicyCard({
  policy,
  expanded,
  onToggleExpand,
  onEdit,
  onDelete,
  invalidatePolicies,
}: {
  policy: InsurancePolicyOut
  expanded: boolean
  onToggleExpand: () => void
  onEdit: () => void
  onDelete: () => void
  invalidatePolicies: () => void
}) {
  const qc = useQueryClient()
  const renewalSoon = isRenewalSoon(policy.renewal_date)

  const premiums = useQuery({
    queryKey: ['insurance-premiums', policy.id],
    queryFn: () => fetchInsurancePremiums(policy.id),
    enabled: expanded,
  })

  const addPremium = useMutation({
    mutationFn: (body: Parameters<typeof postInsurancePremium>[1]) =>
      postInsurancePremium(policy.id, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['insurance-premiums', policy.id] })
      invalidatePolicies()
    },
  })

  const removePremium = useMutation({
    mutationFn: (premiumId: number) => deleteInsurancePremium(policy.id, premiumId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['insurance-premiums', policy.id] })
    },
  })

  return (
    <div className={`rounded-xl border bg-white shadow-sm ${renewalSoon ? 'border-amber-300' : 'border-zinc-200'}`}>
      <div className="flex flex-col gap-2 p-4 sm:flex-row sm:items-start">
        {/* Left: name + badges */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-zinc-900">{policy.name}</span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${typeBadgeColor(policy.type)}`}>
              {policy.type}
            </span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusBadgeColor(policy.status)}`}>
              {policy.status}
            </span>
            {policy.tax_deduction_section ? (
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${taxBadgeColor(policy.tax_deduction_section)}`}>
                {policy.tax_deduction_section}
              </span>
            ) : null}
            {renewalSoon ? (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                Renews soon
              </span>
            ) : null}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-600">
            {policy.provider ? <span>Provider: <span className="font-medium text-zinc-800">{policy.provider}</span></span> : null}
            {policy.policy_number ? <span>Policy #: <span className="font-medium text-zinc-800">{policy.policy_number}</span></span> : null}
            {policy.covered_members ? <span>Covers: <span className="font-medium text-zinc-800">{policy.covered_members}</span></span> : null}
          </div>
        </div>

        {/* Right: numbers */}
        <div className="flex flex-wrap items-start gap-4 sm:shrink-0 sm:text-right">
          <div>
            <p className="text-xs text-zinc-500">Annual premium</p>
            <p className="text-sm font-semibold tabular-nums text-zinc-900">
              {formatPaise(policy.annual_premium_paise)}
            </p>
            <p className="text-xs text-zinc-500 capitalize">{policy.premium_frequency.replace('_', ' ')}</p>
          </div>
          {policy.sum_insured_paise != null ? (
            <div>
              <p className="text-xs text-zinc-500">Sum insured</p>
              <p className="text-sm tabular-nums text-zinc-700">{formatPaiseCompact(policy.sum_insured_paise)}</p>
            </div>
          ) : null}
          {policy.renewal_date ? (
            <div>
              <p className="text-xs text-zinc-500">Renewal</p>
              <p className={`text-sm tabular-nums ${renewalSoon ? 'font-semibold text-amber-700' : 'text-zinc-700'}`}>
                {policy.renewal_date}
              </p>
            </div>
          ) : null}
        </div>
      </div>

      {/* Actions bar */}
      <div className="flex items-center gap-2 border-t border-zinc-100 px-4 py-2">
        <button
          type="button"
          onClick={onToggleExpand}
          className="rounded px-2 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-50"
        >
          {expanded ? 'Hide history' : 'Premium history'}
        </button>
        <button
          type="button"
          onClick={onEdit}
          className="rounded px-2 py-1 text-xs font-medium text-zinc-600 hover:bg-zinc-50"
        >
          Edit
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="rounded px-2 py-1 text-xs text-red-500 hover:bg-red-50"
        >
          Delete
        </button>
      </div>

      {/* Expanded: premium history */}
      {expanded ? (
        <div className="border-t border-zinc-100 px-4 py-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">Premium payment history</p>
          {premiums.isPending ? (
            <p className="text-sm text-zinc-500">Loading…</p>
          ) : premiums.isError ? (
            <p className="text-sm text-red-600">{String(premiums.error)}</p>
          ) : premiums.data.length === 0 ? (
            <p className="mb-3 text-sm text-zinc-500">No payments logged yet.</p>
          ) : (
            <div className="mb-4 overflow-x-auto">
              <table className="w-full min-w-[600px] text-left text-sm">
                <thead className="text-xs font-semibold text-zinc-600">
                  <tr>
                    <th className="pb-1.5">Date</th>
                    <th className="pb-1.5 text-right">Amount</th>
                    <th className="pb-1.5">Period</th>
                    <th className="pb-1.5">Mode</th>
                    <th className="pb-1.5">Reference</th>
                    <th className="pb-1.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {premiums.data.map((pr) => (
                    <PremiumRow
                      key={pr.id}
                      premium={pr}
                      onDelete={() => {
                        if (window.confirm('Delete this premium payment?')) {
                          removePremium.mutate(pr.id)
                        }
                      }}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <AddPremiumForm
            onAdd={(body) => addPremium.mutate(body)}
            isPending={addPremium.isPending}
            error={addPremium.isError ? String(addPremium.error) : null}
          />
        </div>
      ) : null}
    </div>
  )
}

function PremiumRow({ premium, onDelete }: { premium: InsurancePremiumOut; onDelete: () => void }) {
  const period = premium.period_start && premium.period_end
    ? `${premium.period_start} – ${premium.period_end}`
    : (premium.period_start ?? premium.period_end ?? '—')
  return (
    <tr className="text-zinc-800 hover:bg-zinc-50">
      <td className="py-1.5">{premium.payment_date}</td>
      <td className="py-1.5 text-right tabular-nums">{formatPaise(premium.amount_paise)}</td>
      <td className="py-1.5 text-zinc-600 text-xs">{period}</td>
      <td className="py-1.5 text-zinc-500 text-xs">{premium.payment_mode ?? '—'}</td>
      <td className="py-1.5 text-zinc-500 text-xs">{premium.reference_number ?? '—'}</td>
      <td className="py-1.5">
        <button type="button" onClick={onDelete} className="rounded px-1.5 py-0.5 text-xs text-red-500 hover:bg-red-50">
          Delete
        </button>
      </td>
    </tr>
  )
}

function AddPremiumForm({
  onAdd,
  isPending,
  error,
}: {
  onAdd: (body: Parameters<typeof postInsurancePremium>[1]) => void
  isPending: boolean
  error: string | null
}) {
  const [paymentDate, setPaymentDate] = useState('')
  const [amount, setAmount] = useState('')
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [paymentMode, setPaymentMode] = useState('')
  const [refNumber, setRefNumber] = useState('')
  const [notes, setNotes] = useState('')

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    const ap = rupeesToPaise(amount)
    if (ap == null || !paymentDate.trim()) return
    onAdd({
      payment_date: paymentDate,
      amount_paise: ap,
      period_start: periodStart.trim() || null,
      period_end: periodEnd.trim() || null,
      payment_mode: paymentMode.trim() || null,
      reference_number: refNumber.trim() || null,
      notes: notes.trim() || null,
    })
    setPaymentDate('')
    setAmount('')
    setPeriodStart('')
    setPeriodEnd('')
    setPaymentMode('')
    setRefNumber('')
    setNotes('')
  }

  return (
    <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-2">
      <label className="text-xs font-medium text-zinc-600">
        Payment date *
        <input type="date" className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} required />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Amount (₹) *
        <input className="mt-1 w-28 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Period start
        <input type="date" className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Period end
        <input type="date" className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Mode
        <input className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={paymentMode} placeholder="UPI/NEFT/…" onChange={(e) => setPaymentMode(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Reference
        <input className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={refNumber} onChange={(e) => setRefNumber(e.target.value)} />
      </label>
      <button
        type="submit"
        disabled={isPending}
        className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
      >
        Log payment
      </button>
      {error ? <p className="w-full text-sm text-red-600">{error}</p> : null}
    </form>
  )
}

// ── Policy form modal (shared for add + edit) ─────────────────────────────────

function PolicyFormModal({
  title,
  initialData,
  onClose,
  onSubmit,
  isPending,
  error,
}: {
  title: string
  initialData: InsurancePolicyOut | null
  onClose: () => void
  onSubmit: (body: Record<string, unknown>) => void
  isPending: boolean
  error: string | null
}) {
  const [name, setName] = useState(initialData?.name ?? '')
  const [type, setType] = useState(initialData?.type ?? POLICY_TYPES[0])
  const [provider, setProvider] = useState(initialData?.provider ?? '')
  const [policyNumber, setPolicyNumber] = useState(initialData?.policy_number ?? '')
  const [sumInsured, setSumInsured] = useState(paiseToRupees(initialData?.sum_insured_paise))
  const [premium, setPremium] = useState(paiseToRupees(initialData?.premium_paise))
  const [premiumFrequency, setPremiumFrequency] = useState(
    initialData?.premium_frequency ?? PREMIUM_FREQUENCIES[0],
  )
  const [startDate, setStartDate] = useState(initialData?.start_date ?? '')
  const [endDate, setEndDate] = useState(initialData?.end_date ?? '')
  const [renewalDate, setRenewalDate] = useState(initialData?.renewal_date ?? '')
  const [policyholder, setPolicyholder] = useState(initialData?.policyholder ?? 'Self')
  const [coveredMembers, setCoveredMembers] = useState(initialData?.covered_members ?? '')
  const [taxSection, setTaxSection] = useState(initialData?.tax_deduction_section ?? '')
  const [status, setStatus] = useState(initialData?.status ?? 'active')
  const [notes, setNotes] = useState(initialData?.notes ?? '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const si = sumInsured.trim() === '' ? null : rupeesToPaise(sumInsured)
    const pr = rupeesToPaise(premium)
    if (pr == null) return
    if (sumInsured.trim() !== '' && si == null) return

    onSubmit({
      name: name.trim() || 'Policy',
      type,
      provider: provider.trim() || null,
      policy_number: policyNumber.trim() || null,
      sum_insured_paise: si,
      premium_paise: pr,
      premium_frequency: premiumFrequency,
      start_date: startDate.trim() || null,
      end_date: endDate.trim() || null,
      renewal_date: renewalDate.trim() || null,
      policyholder: policyholder.trim() || 'Self',
      covered_members: coveredMembers.trim() || null,
      tax_deduction_section: taxSection.trim() || null,
      status,
      notes: notes.trim() || null,
    })
  }

  const inputCls = 'mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm text-zinc-900'
  const inputNumCls = `${inputCls} text-right tabular-nums`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-zinc-900">{title}</h2>
        <form onSubmit={handleSubmit}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="col-span-2 text-xs font-medium text-zinc-600">
              Policy name *
              <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Type
              <select className={inputCls} value={type} onChange={(e) => setType(e.target.value)}>
                {POLICY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Status
              <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
                {POLICY_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Provider / Insurer
              <input className={inputCls} value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="optional" />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Policy number
              <input className={inputCls} value={policyNumber} onChange={(e) => setPolicyNumber(e.target.value)} placeholder="optional" />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Premium (₹) *
              <input className={inputNumCls} inputMode="decimal" value={premium} onChange={(e) => setPremium(e.target.value)} required />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Frequency
              <select className={inputCls} value={premiumFrequency} onChange={(e) => setPremiumFrequency(e.target.value)}>
                {PREMIUM_FREQUENCIES.map((f) => <option key={f} value={f}>{f.replace('_', ' ')}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Sum insured (₹)
              <input className={inputNumCls} inputMode="decimal" value={sumInsured} onChange={(e) => setSumInsured(e.target.value)} placeholder="optional" />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Tax deduction section
              <select className={inputCls} value={taxSection} onChange={(e) => setTaxSection(e.target.value)}>
                <option value="">None</option>
                {TAX_SECTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Policyholder
              <input className={inputCls} value={policyholder} onChange={(e) => setPolicyholder(e.target.value)} placeholder="Self" />
            </label>
            <label className="col-span-2 text-xs font-medium text-zinc-600">
              Covered members
              <input className={inputCls} value={coveredMembers} onChange={(e) => setCoveredMembers(e.target.value)} placeholder="e.g. Self, Spouse, Child — optional" />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Start date
              <input type="date" className={inputCls} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              End date
              <input type="date" className={inputCls} value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </label>
            <label className="col-span-2 text-xs font-medium text-zinc-600">
              Renewal date
              <input type="date" className={inputCls} value={renewalDate} onChange={(e) => setRenewalDate(e.target.value)} />
            </label>
            <label className="col-span-2 text-xs font-medium text-zinc-600">
              Notes
              <textarea
                className={`${inputCls} resize-none`}
                rows={2}
                placeholder="optional"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
          </div>
          {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {isPending ? 'Saving…' : initialData ? 'Save changes' : 'Add policy'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
