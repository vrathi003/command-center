import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  deleteAssetCost,
  deleteAssetLoan,
  deleteAssetPayment,
  deleteDisbursal,
  fetchAssetDetail,
  fetchDebtAmortization,
  fetchDisbursals,
  fetchDebts,
  postAssetCost,
  postAssetLoan,
  postAssetPayment,
  putAssetPayment,
  postDisbursal,
  putAsset,
  putAssetCost,
  putRealEstate,
  putVehicle,
} from '@/lib/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'
import type {
  AmortizationRow,
  AssetCostOut,
  AssetDetailOut,
  AssetLoanOut,
  AssetPaymentOut,
  DebtOut,
  LoanDisbursalOut,
} from '@/types/api'
import type { AssetPaymentBody } from '@/lib/api'

const ASSET_TYPES = ['apartment', 'plot', 'commercial', 'vehicle', 'gold', 'other'] as const
const ASSET_STATUSES = ['active', 'sold'] as const
const POSSESSION_STATUSES = ['under_construction', 'possessed', 'na'] as const
const AREA_TYPES = ['carpet', 'builtin', 'super_builtin'] as const
const FUEL_TYPES = ['petrol', 'diesel', 'electric', 'cng', 'hybrid', 'other'] as const

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) return null
  return Math.round(n * 100)
}

/** Empty → 0; use for self-funded / loan split so one side can be blank. */
function rupeesToPaiseOrZero(s: string): number | null {
  const t = s.trim()
  if (t === '') return 0
  return rupeesToPaise(t)
}

function paiseToRupees(p: number | null | undefined): string {
  if (p == null || Number.isNaN(p)) return ''
  return String(p / 100)
}

/** Cash/loan paise from API (handles missing keys from older responses). */
function resolvedSplitPaise(p: AssetPaymentOut): { cash: number; loan: number; total: number } {
  let cash = p.amount_cash_paise
  let loan = p.amount_loan_paise
  const total =
    typeof p.amount_paise === 'number' && !Number.isNaN(p.amount_paise) ? p.amount_paise : 0
  if (typeof cash !== 'number' || Number.isNaN(cash)) cash = 0
  if (typeof loan !== 'number' || Number.isNaN(loan)) loan = 0
  if (cash === 0 && loan === 0 && total > 0) {
    if (p.fund_source === 'bank_loan') loan = total
    else cash = total
  }
  return { cash, loan, total }
}

function typeBadge(type: string): string {
  switch (type) {
    case 'apartment': return 'bg-blue-100 text-blue-800'
    case 'plot': return 'bg-emerald-100 text-emerald-800'
    case 'commercial': return 'bg-purple-100 text-purple-800'
    case 'vehicle': return 'bg-amber-100 text-amber-800'
    case 'gold': return 'bg-yellow-100 text-yellow-800'
    default: return 'bg-zinc-100 text-zinc-700'
  }
}

const inputCls = 'mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm text-zinc-900 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500'
const inputNumCls = `${inputCls} text-right tabular-nums`

export function AssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const id = Number(assetId)
  const qc = useQueryClient()

  const detail = useQuery({
    queryKey: ['asset-detail', id],
    queryFn: () => fetchAssetDetail(id),
    enabled: !Number.isNaN(id),
  })

  const debts = useQuery({
    queryKey: ['debts'],
    queryFn: fetchDebts,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['asset-detail', id] })
    void qc.invalidateQueries({ queryKey: ['assets'] })
    void qc.invalidateQueries({ queryKey: ['asset-summary'] })
  }

  const updateAsset = useMutation({
    mutationFn: (body: Parameters<typeof putAsset>[1]) => putAsset(id, body),
    onSuccess: invalidate,
  })

  const updateRE = useMutation({
    mutationFn: (body: Parameters<typeof putRealEstate>[1]) => putRealEstate(id, body),
    onSuccess: invalidate,
  })

  const updateVehicle = useMutation({
    mutationFn: (body: Parameters<typeof putVehicle>[1]) => putVehicle(id, body),
    onSuccess: invalidate,
  })

  const addCost = useMutation({
    mutationFn: (body: Parameters<typeof postAssetCost>[1]) => postAssetCost(id, body),
    onSuccess: invalidate,
  })

  const updateCost = useMutation({
    mutationFn: ({ costId, body }: { costId: number; body: Parameters<typeof putAssetCost>[2] }) =>
      putAssetCost(id, costId, body),
    onSuccess: invalidate,
  })

  const removeCost = useMutation({
    mutationFn: (costId: number) => deleteAssetCost(id, costId),
    onSuccess: invalidate,
  })

  const addLoan = useMutation({
    mutationFn: (body: Parameters<typeof postAssetLoan>[1]) => postAssetLoan(id, body),
    onSuccess: invalidate,
  })

  const removeLoan = useMutation({
    mutationFn: (loanId: number) => deleteAssetLoan(id, loanId),
    onSuccess: invalidate,
  })

  const addPayment = useMutation({
    mutationFn: (body: Parameters<typeof postAssetPayment>[1]) => postAssetPayment(id, body),
    onSuccess: invalidate,
  })

  const removePayment = useMutation({
    mutationFn: (paymentId: number) => deleteAssetPayment(id, paymentId),
    onSuccess: invalidate,
  })

  const updatePayment = useMutation({
    mutationFn: ({ paymentId, body }: { paymentId: number; body: AssetPaymentBody }) =>
      putAssetPayment(id, paymentId, body),
    onSuccess: invalidate,
  })

  if (detail.isPending) return <PageLoading lines={5} />
  if (detail.isError) {
    return (
      <PageError
        title="Could not load asset"
        message={<p className="text-sm">{String(detail.error)}</p>}
      />
    )
  }

  const d: AssetDetailOut = detail.data
  const { asset, real_estate: re, vehicle, costs, loans, payments } = d
  const isRealEstate = ['apartment', 'plot', 'commercial'].includes(asset.type)
  const isVehicle = asset.type === 'vehicle'

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to="/assets"
          className="rounded-lg border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50"
        >
          ← Back
        </Link>
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold text-zinc-900">{asset.name}</h1>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${typeBadge(asset.type)}`}>
            {asset.type}
          </span>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
            asset.status === 'active' ? 'bg-emerald-100 text-emerald-800' : 'bg-zinc-200 text-zinc-600'
          }`}>
            {asset.status}
          </span>
        </div>
      </div>

      {/* Summary KPIs */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          tone="neutral"
          label="Total all-in cost"
          value={formatPaiseCompact(d.total_cost_paise)}
          hint="Cost breakdown + payment milestones"
        />
        <KpiCard
          tone="neutral"
          label="Current value"
          value={asset.current_value_paise != null ? formatPaiseCompact(asset.current_value_paise) : '—'}
        />
        <KpiCard
          tone="neutral"
          label="Milestones paid"
          value={formatPaiseCompact(d.total_paid_paise)}
        />
        <KpiCard
          tone={d.appreciation_pct != null && d.appreciation_pct >= 0 ? 'neutral' : 'spending'}
          label="Appreciation"
          value={d.appreciation_pct != null ? `${d.appreciation_pct >= 0 ? '+' : ''}${d.appreciation_pct.toFixed(1)}%` : '—'}
        />
      </section>

      {/* Overview — edit basic fields */}
      <section>
        <SectionTitle>Overview</SectionTitle>
        <Panel>
          <OverviewForm
            asset={asset}
            onSave={(body) => updateAsset.mutate(body)}
            isPending={updateAsset.isPending}
            error={updateAsset.isError ? String(updateAsset.error) : null}
          />
        </Panel>
      </section>

      {/* Real estate details */}
      {isRealEstate ? (
        <section>
          <SectionTitle>Property details</SectionTitle>
          <Panel>
            <RealEstateForm
              re={re}
              onSave={(body) => updateRE.mutate(body)}
              isPending={updateRE.isPending}
              error={updateRE.isError ? String(updateRE.error) : null}
            />
          </Panel>
        </section>
      ) : null}

      {/* Vehicle details */}
      {isVehicle ? (
        <section>
          <SectionTitle>Vehicle details</SectionTitle>
          <Panel>
            <VehicleForm
              vehicle={vehicle}
              onSave={(body) => updateVehicle.mutate(body)}
              isPending={updateVehicle.isPending}
              error={updateVehicle.isError ? String(updateVehicle.error) : null}
            />
          </Panel>
        </section>
      ) : null}

      {/* Cost breakdown */}
      <section>
        <SectionTitle>Cost breakdown</SectionTitle>
        <Panel variant="table" padding={false}>
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-600">
              <tr>
                <th className="px-4 py-2.5">Cost type</th>
                <th className="px-4 py-2.5 text-right">Amount</th>
                <th className="px-4 py-2.5">Paid date</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Notes</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {costs.map((c) => (
                <CostRow
                  key={c.id}
                  cost={c}
                  onUpdate={(body) => updateCost.mutate({ costId: c.id, body })}
                  onDelete={() => {
                    if (window.confirm('Delete this cost entry?')) {
                      removeCost.mutate(c.id)
                    }
                  }}
                />
              ))}
              {costs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-4 text-center text-zinc-500">
                    No cost entries yet
                  </td>
                </tr>
              ) : null}
            </tbody>
            <tfoot className="border-t-2 border-zinc-300 bg-zinc-50">
              {(() => {
                const paidTotal = costs.filter((c) => c.is_paid).reduce((s, c) => s + c.amount_paise, 0)
                const upcomingTotal = costs.filter((c) => !c.is_paid).reduce((s, c) => s + c.amount_paise, 0)
                return (
                  <>
                    <tr>
                      <td className="px-4 py-2 text-xs font-medium text-zinc-600">Paid so far</td>
                      <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-emerald-700">{formatPaise(paidTotal)}</td>
                      <td colSpan={4} />
                    </tr>
                    {upcomingTotal > 0 && (
                      <tr>
                        <td className="px-4 py-2 text-xs font-medium text-zinc-600">Upcoming</td>
                        <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-amber-700">{formatPaise(upcomingTotal)}</td>
                        <td colSpan={4} />
                      </tr>
                    )}
                    <tr className="border-t border-zinc-200">
                      <td className="px-4 py-2.5 text-sm font-bold text-zinc-800">Subtotal (cost breakdown)</td>
                      <td className="px-4 py-2.5 text-right text-sm font-bold tabular-nums text-zinc-900">{formatPaise(paidTotal + upcomingTotal)}</td>
                      <td colSpan={4} />
                    </tr>
                  </>
                )
              })()}
            </tfoot>
          </table>
          <div className="border-t border-zinc-100 px-4 py-3">
            <AddCostForm
              onAdd={(body) => addCost.mutate(body)}
              isPending={addCost.isPending}
              error={addCost.isError ? String(addCost.error) : null}
            />
          </div>
        </Panel>
      </section>

      {/* Loan links */}
      <section>
        <SectionTitle>Linked loans</SectionTitle>
        <div className="space-y-4">
          {loans.length === 0 ? (
            <Panel>
              <p className="mb-4 text-sm text-zinc-500">No loans linked to this asset.</p>
              <AddLoanForm
                debtOptions={debts.data ?? []}
                onAdd={(body) => addLoan.mutate(body)}
                isPending={addLoan.isPending}
                error={addLoan.isError ? String(addLoan.error) : null}
              />
            </Panel>
          ) : (
            <>
              {loans.map((l) => (
                <LinkedLoanCard
                  key={l.id}
                  loan={l}
                  debt={debts.data?.find((d) => d.id === l.debt_id) ?? null}
                  onUnlink={() => {
                    if (window.confirm('Unlink this loan?')) removeLoan.mutate(l.id)
                  }}
                />
              ))}
              <Panel>
                <AddLoanForm
                  debtOptions={debts.data ?? []}
                  onAdd={(body) => addLoan.mutate(body)}
                  isPending={addLoan.isPending}
                  error={addLoan.isError ? String(addLoan.error) : null}
                />
              </Panel>
            </>
          )}
        </div>
      </section>

      {/* Payment milestones — same table as cost breakdown style; Source column = Cash vs bank loan */}
      <section>
        <SectionTitle>Payment milestones</SectionTitle>
        <p className="text-sm text-zinc-600">
          Split each milestone into <strong>self-funded</strong> and <strong>loan</strong> amounts; <strong>Total</strong>{' '}
          is the sum. <strong>Source</strong> is a quick tag (Cash vs loan). Use <strong>Paid</strong> /{' '}
          <strong>Upcoming</strong> and set <strong>due date</strong> / <strong>paid date</strong> as needed.
        </p>
        <PaymentMilestonesTable
          payments={payments}
          onAdd={(body) => addPayment.mutate(body)}
          onUpdate={(paymentId, body) => updatePayment.mutate({ paymentId, body })}
          onDelete={(paymentId) => {
            if (window.confirm('Delete this payment?')) {
              removePayment.mutate(paymentId)
            }
          }}
          addPending={addPayment.isPending}
          updatePending={updatePayment.isPending}
          addError={addPayment.isError ? String(addPayment.error) : null}
          updateError={updatePayment.isError ? String(updatePayment.error) : null}
          totalPaidPaise={d.total_paid_paise}
          totalUpcomingPaise={d.total_payment_milestones_upcoming_paise}
        />
      </section>
    </div>
  )
}

// ── Sub-components ───────────────────────────────────────────────────────────

function OverviewForm({
  asset,
  onSave,
  isPending,
  error,
}: {
  asset: AssetDetailOut['asset']
  onSave: (body: Parameters<typeof putAsset>[1]) => void
  isPending: boolean
  error: string | null
}) {
  const [name, setName] = useState(asset.name)
  const [type, setType] = useState(asset.type)
  const [status, setStatus] = useState(asset.status)
  const [purchaseDate, setPurchaseDate] = useState(asset.purchase_date ?? '')
  const [purchasePrice, setPurchasePrice] = useState(paiseToRupees(asset.purchase_price_paise))
  const [currentValue, setCurrentValue] = useState(paiseToRupees(asset.current_value_paise))
  const [ownershipPct, setOwnershipPct] = useState(String(asset.ownership_percent))
  const [coOwner, setCoOwner] = useState(asset.co_owner ?? '')
  const [notes, setNotes] = useState(asset.notes ?? '')

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    const pp = purchasePrice.trim() === '' ? null : rupeesToPaise(purchasePrice)
    const cv = currentValue.trim() === '' ? null : rupeesToPaise(currentValue)
    const ownershipNum = Number.parseFloat(ownershipPct)
    if (purchasePrice.trim() !== '' && pp == null) return
    if (currentValue.trim() !== '' && cv == null) return
    if (Number.isNaN(ownershipNum)) return
    onSave({
      name: name.trim() || asset.name,
      type,
      status,
      purchase_date: purchaseDate.trim() || null,
      purchase_price_paise: pp,
      current_value_paise: cv,
      ownership_percent: ownershipNum,
      co_owner: coOwner.trim() || null,
      notes: notes.trim() || null,
    })
  }

  return (
    <form onSubmit={handleSave} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label className="text-xs font-medium text-zinc-600">
        Name *
        <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Type
        <select className={inputCls} value={type} onChange={(e) => setType(e.target.value)}>
          {ASSET_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Status
        <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
          {ASSET_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Purchase date
        <input type="date" className={inputCls} value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Ownership %
        <input className={inputNumCls} inputMode="decimal" value={ownershipPct} onChange={(e) => setOwnershipPct(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Co-owner
        <input className={inputCls} value={coOwner} placeholder="optional" onChange={(e) => setCoOwner(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Purchase price (₹)
        <input className={inputNumCls} inputMode="decimal" placeholder="optional" value={purchasePrice} onChange={(e) => setPurchasePrice(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Current value (₹)
        <input className={inputNumCls} inputMode="decimal" placeholder="optional" value={currentValue} onChange={(e) => setCurrentValue(e.target.value)} />
      </label>
      <label className="sm:col-span-2 lg:col-span-3 text-xs font-medium text-zinc-600">
        Notes
        <textarea
          className={`${inputCls} resize-none`}
          rows={2}
          placeholder="optional"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      {error ? <p className="col-span-full text-sm text-red-600">{error}</p> : null}
      <div className="flex items-center">
        <button
          type="submit"
          disabled={isPending}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
        >
          {isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </form>
  )
}

function RealEstateForm({
  re,
  onSave,
  isPending,
  error,
}: {
  re: AssetDetailOut['real_estate']
  onSave: (body: Parameters<typeof putRealEstate>[1]) => void
  isPending: boolean
  error: string | null
}) {
  // Area: display whichever area column the PSF type matches; fall back to first non-null
  const initArea = (): string => {
    if (re == null) return ''
    if (re.psf_area_type === 'carpet' && re.carpet_area_sqft != null) return String(re.carpet_area_sqft)
    if (re.psf_area_type === 'builtin' && re.builtin_area_sqft != null) return String(re.builtin_area_sqft)
    if (re.psf_area_type === 'super_builtin' && re.super_builtin_area_sqft != null) return String(re.super_builtin_area_sqft)
    return String(re.carpet_area_sqft ?? re.builtin_area_sqft ?? re.super_builtin_area_sqft ?? '')
  }

  const [projectName, setProjectName] = useState(re?.project_name ?? '')
  const [builder, setBuilder] = useState(re?.builder ?? '')
  const [city, setCity] = useState(re?.city ?? '')
  const [state, setState] = useState(re?.state ?? '')
  const [address, setAddress] = useState(re?.address ?? '')
  const [pinCode, setPinCode] = useState(re?.pin_code ?? '')
  const [unitDetails, setUnitDetails] = useState(re?.unit_details ?? '')
  const [areaSqft, setAreaSqft] = useState(initArea)
  const [areaType, setAreaType] = useState(re?.psf_area_type ?? AREA_TYPES[0])
  // PSF stored in paise → display in rupees
  const [psfPurchase, setPsfPurchase] = useState(re?.purchase_psf_paise != null ? String(re.purchase_psf_paise / 100) : '')
  const [psfCurrent, setPsfCurrent] = useState(re?.current_psf_paise != null ? String(re.current_psf_paise / 100) : '')
  const [possessionStatus, setPossessionStatus] = useState(re?.possession_status ?? POSSESSION_STATUSES[0])
  const [possessionDateEst, setPossessionDateEst] = useState(re?.possession_date_estimated ?? '')
  const [possessionDateActual, setPossessionDateActual] = useState(re?.possession_date_actual ?? '')
  const [agreementValue, setAgreementValue] = useState(re?.agreement_value_paise != null ? String(re.agreement_value_paise / 100) : '')

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    const area = areaSqft.trim() === '' ? null : Number.parseFloat(areaSqft)
    const areaVal = area != null && !Number.isNaN(area) ? area : null
    // Set the right area column based on area type
    const carpetArea = areaType === 'carpet' ? areaVal : null
    const builtinArea = areaType === 'builtin' ? areaVal : null
    const superBuiltinArea = areaType === 'super_builtin' ? areaVal : null
    const psfP = psfPurchase.trim() === '' ? null : Math.round(Number.parseFloat(psfPurchase) * 100)
    const psfC = psfCurrent.trim() === '' ? null : Math.round(Number.parseFloat(psfCurrent) * 100)
    const agrVal = agreementValue.trim() === '' ? null : Math.round(Number.parseFloat(agreementValue) * 100)
    onSave({
      project_name: projectName.trim() || null,
      builder: builder.trim() || null,
      city: city.trim() || null,
      state: state.trim() || null,
      address: address.trim() || null,
      pin_code: pinCode.trim() || null,
      unit_details: unitDetails.trim() || null,
      carpet_area_sqft: carpetArea,
      builtin_area_sqft: builtinArea,
      super_builtin_area_sqft: superBuiltinArea,
      psf_area_type: areaType,
      purchase_psf_paise: psfP != null && !Number.isNaN(psfP) ? psfP : null,
      current_psf_paise: psfC != null && !Number.isNaN(psfC) ? psfC : null,
      possession_status: possessionStatus,
      possession_date_estimated: possessionDateEst.trim() || null,
      possession_date_actual: possessionDateActual.trim() || null,
      agreement_value_paise: agrVal != null && !Number.isNaN(agrVal) ? agrVal : null,
      circle_rate_psf_paise: null,
    })
  }

  return (
    <form onSubmit={handleSave} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label className="text-xs font-medium text-zinc-600">
        Project name
        <input className={inputCls} value={projectName} onChange={(e) => setProjectName(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Builder / Developer
        <input className={inputCls} value={builder} onChange={(e) => setBuilder(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        City
        <input className={inputCls} value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Bengaluru" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        State
        <input className={inputCls} value={state} onChange={(e) => setState(e.target.value)} placeholder="e.g. Karnataka" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Address / Locality
        <input className={inputCls} value={address} onChange={(e) => setAddress(e.target.value)} placeholder="e.g. Whitefield" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        PIN code
        <input className={inputCls} value={pinCode} onChange={(e) => setPinCode(e.target.value)} placeholder="e.g. 560066" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Unit / Floor details
        <input className={inputCls} value={unitDetails} onChange={(e) => setUnitDetails(e.target.value)} placeholder="e.g. Tower B, 12th floor, Flat 1204" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Area (sqft)
        <input className={inputNumCls} inputMode="decimal" value={areaSqft} onChange={(e) => setAreaSqft(e.target.value)} placeholder="e.g. 1200" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Area type
        <select className={inputCls} value={areaType} onChange={(e) => setAreaType(e.target.value)}>
          <option value="carpet">Carpet</option>
          <option value="builtin">Built-in</option>
          <option value="super_builtin">Super built-in</option>
        </select>
      </label>
      <label className="text-xs font-medium text-zinc-600">
        PSF purchase price (₹/sqft)
        <input className={inputNumCls} inputMode="decimal" value={psfPurchase} onChange={(e) => setPsfPurchase(e.target.value)} placeholder="e.g. 7500" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        PSF current price (₹/sqft)
        <input className={inputNumCls} inputMode="decimal" value={psfCurrent} onChange={(e) => setPsfCurrent(e.target.value)} placeholder="e.g. 9000" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Agreement value (₹)
        <input className={inputNumCls} inputMode="decimal" value={agreementValue} onChange={(e) => setAgreementValue(e.target.value)} placeholder="optional" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Possession status
        <select className={inputCls} value={possessionStatus} onChange={(e) => setPossessionStatus(e.target.value)}>
          <option value="under_construction">Under construction</option>
          <option value="possessed">Possessed</option>
          <option value="na">N/A</option>
        </select>
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Estimated possession date
        <input type="date" className={inputCls} value={possessionDateEst} onChange={(e) => setPossessionDateEst(e.target.value)} />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Actual possession date
        <input type="date" className={inputCls} value={possessionDateActual} onChange={(e) => setPossessionDateActual(e.target.value)} />
      </label>
      {error ? <p className="col-span-full text-sm text-red-600">{error}</p> : null}
      <div className="col-span-full flex items-center">
        <button
          type="submit"
          disabled={isPending}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
        >
          {isPending ? 'Saving…' : 'Save property details'}
        </button>
      </div>
    </form>
  )
}

function VehicleForm({
  vehicle,
  onSave,
  isPending,
  error,
}: {
  vehicle: AssetDetailOut['vehicle']
  onSave: (body: Parameters<typeof putVehicle>[1]) => void
  isPending: boolean
  error: string | null
}) {
  const [make, setMake] = useState(vehicle?.make ?? '')
  const [model, setModel] = useState(vehicle?.model ?? '')
  const [variant, setVariant] = useState(vehicle?.variant ?? '')
  const [color, setColor] = useState(vehicle?.color ?? '')
  const [year, setYear] = useState(vehicle?.year != null ? String(vehicle.year) : '')
  const [regNumber, setRegNumber] = useState(vehicle?.registration_number ?? '')
  const [fuelType, setFuelType] = useState(vehicle?.fuel_type ?? FUEL_TYPES[0])
  const [depRate, setDepRate] = useState(String(vehicle?.depreciation_rate_percent ?? 15))

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    const y = year.trim() === '' ? null : Number.parseInt(year, 10)
    const dep = Number.parseFloat(depRate)
    onSave({
      make: make.trim() || null,
      model: model.trim() || null,
      variant: variant.trim() || null,
      color: color.trim() || null,
      year: y != null && !Number.isNaN(y) ? y : null,
      registration_number: regNumber.trim() || null,
      fuel_type: fuelType || null,
      depreciation_rate_percent: !Number.isNaN(dep) ? dep : 15,
    })
  }

  return (
    <form onSubmit={handleSave} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label className="text-xs font-medium text-zinc-600">
        Make
        <input className={inputCls} value={make} onChange={(e) => setMake(e.target.value)} placeholder="e.g. Maruti" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Model
        <input className={inputCls} value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. Swift" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Variant
        <input className={inputCls} value={variant} onChange={(e) => setVariant(e.target.value)} placeholder="e.g. ZXi+" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Color
        <input className={inputCls} value={color} onChange={(e) => setColor(e.target.value)} placeholder="e.g. Pearl White" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Year
        <input className={inputNumCls} inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} placeholder="e.g. 2022" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Registration number
        <input className={inputCls} value={regNumber} onChange={(e) => setRegNumber(e.target.value)} placeholder="e.g. KA01AB1234" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Fuel type
        <select className={inputCls} value={fuelType} onChange={(e) => setFuelType(e.target.value)}>
          {FUEL_TYPES.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Depreciation rate (% p.a.)
        <input className={inputNumCls} inputMode="decimal" value={depRate} onChange={(e) => setDepRate(e.target.value)} placeholder="15" />
      </label>
      {error ? <p className="col-span-full text-sm text-red-600">{error}</p> : null}
      <div className="col-span-full flex items-center">
        <button
          type="submit"
          disabled={isPending}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
        >
          {isPending ? 'Saving…' : 'Save vehicle details'}
        </button>
      </div>
    </form>
  )
}

type CostUpdateBody = Parameters<typeof putAssetCost>[2]

function CostRow({
  cost,
  onUpdate,
  onDelete,
}: {
  cost: AssetCostOut
  onUpdate: (body: CostUpdateBody) => void
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [costType, setCostType] = useState(cost.cost_type)
  const [amount, setAmount] = useState(paiseToRupees(cost.amount_paise))
  const [paidDate, setPaidDate] = useState(cost.paid_date ?? '')
  const [description, setDescription] = useState(cost.description ?? '')
  const [isPaid, setIsPaid] = useState(cost.is_paid)

  // Reset local state whenever cost prop changes (after a successful save)
  const prevId = cost.id
  if (prevId !== cost.id) {
    setCostType(cost.cost_type)
    setAmount(paiseToRupees(cost.amount_paise))
    setPaidDate(cost.paid_date ?? '')
    setDescription(cost.description ?? '')
    setIsPaid(cost.is_paid)
  }

  const handleSave = () => {
    const ap = rupeesToPaise(amount)
    if (ap == null || !costType.trim()) return
    onUpdate({
      cost_type: costType.trim(),
      amount_paise: ap,
      paid_date: paidDate.trim() || null,
      description: description.trim() || null,
      is_paid: isPaid,
    })
    setEditing(false)
  }

  const handleCancel = () => {
    setCostType(cost.cost_type)
    setAmount(paiseToRupees(cost.amount_paise))
    setPaidDate(cost.paid_date ?? '')
    setDescription(cost.description ?? '')
    setIsPaid(cost.is_paid)
    setEditing(false)
  }

  // ── View mode ──
  if (!editing) {
    return (
      <tr
        className={`group cursor-pointer text-zinc-800 hover:bg-zinc-50 ${!cost.is_paid ? 'opacity-80' : ''}`}
        onClick={() => setEditing(true)}
      >
        <td className="px-4 py-2.5 font-medium">
          {cost.cost_type}
          <span className="ml-2 hidden text-[10px] text-zinc-400 group-hover:inline">✎ edit</span>
        </td>
        <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${cost.is_paid ? 'text-zinc-900' : 'text-amber-700'}`}>
          {formatPaise(cost.amount_paise)}
        </td>
        <td className="px-4 py-2.5 text-xs text-zinc-500">{cost.paid_date ?? '—'}</td>
        <td className="px-4 py-2.5">
          {cost.is_paid ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
              ✓ Paid
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
              ⏳ Upcoming
            </span>
          )}
        </td>
        <td className="px-4 py-2.5 text-xs text-zinc-400">{cost.description ?? ''}</td>
        <td className="px-4 py-2.5 text-right">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onDelete() }}
            className="rounded px-2 py-0.5 text-xs text-red-400 opacity-0 hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
          >
            Delete
          </button>
        </td>
      </tr>
    )
  }

  // ── Edit mode ──
  const cellCls = 'px-2 py-1.5'
  const editInput = 'w-full rounded border border-emerald-400 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500'

  return (
    <tr className="bg-emerald-50 ring-1 ring-inset ring-emerald-200">
      <td className={cellCls}>
        <input
          list="cost-type-list"
          className={editInput}
          value={costType}
          onChange={(e) => setCostType(e.target.value)}
          autoFocus
          onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') handleCancel() }}
        />
      </td>
      <td className={cellCls}>
        <input
          className={`${editInput} text-right tabular-nums`}
          inputMode="decimal"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') handleCancel() }}
        />
      </td>
      <td className={cellCls}>
        <input
          type="date"
          className={editInput}
          value={paidDate}
          onChange={(e) => setPaidDate(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Escape') handleCancel() }}
        />
      </td>
      <td className={cellCls}>
        <button
          type="button"
          onClick={() => setIsPaid((v) => !v)}
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
            isPaid
              ? 'bg-emerald-200 text-emerald-800 hover:bg-emerald-300'
              : 'bg-amber-200 text-amber-800 hover:bg-amber-300'
          }`}
        >
          <span className={`h-2 w-2 rounded-full ${isPaid ? 'bg-emerald-600' : 'bg-amber-500'}`} />
          {isPaid ? 'Paid' : 'Upcoming'}
        </button>
      </td>
      <td className={cellCls}>
        <input
          className={editInput}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="optional note"
          onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') handleCancel() }}
        />
      </td>
      <td className={`${cellCls} text-right`}>
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={handleSave}
            className="rounded bg-emerald-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-800"
          >
            Save
          </button>
          <button
            type="button"
            onClick={handleCancel}
            className="rounded border border-zinc-300 px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100"
          >
            ✕
          </button>
        </div>
      </td>
    </tr>
  )
}

const COST_TYPE_SUGGESTIONS = [
  'Base price', 'Stamp duty', 'Registration', 'GST', 'Brokerage', 'Parking',
  'Interiors', 'Club membership', 'Legal fees', 'Maintenance deposit',
  'Power backup', 'EV charging', 'Loan processing fee', 'Insurance',
]

function AddCostForm({
  onAdd,
  isPending,
  error,
}: {
  onAdd: (body: { cost_type: string; amount_paise: number; paid_date?: string | null; description?: string | null; is_paid?: boolean }) => void
  isPending: boolean
  error: string | null
}) {
  const [costType, setCostType] = useState('')
  const [amount, setAmount] = useState('')
  const [paidDate, setPaidDate] = useState('')
  const [description, setDescription] = useState('')
  const [isPaid, setIsPaid] = useState(true)

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    const ap = rupeesToPaise(amount)
    if (ap == null || !costType.trim()) return
    onAdd({
      cost_type: costType.trim(),
      amount_paise: ap,
      paid_date: paidDate.trim() || null,
      description: description.trim() || null,
      is_paid: isPaid,
    })
    setCostType('')
    setAmount('')
    setPaidDate('')
    setDescription('')
    setIsPaid(true)
  }

  return (
    <form onSubmit={handleAdd} className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Add cost entry</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs font-medium text-zinc-600">
          Cost type *
          <input
            list="cost-type-list"
            className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm w-44"
            value={costType}
            onChange={(e) => setCostType(e.target.value)}
            placeholder="e.g. Stamp duty"
            required
          />
          <datalist id="cost-type-list">
            {COST_TYPE_SUGGESTIONS.map((s) => <option key={s} value={s} />)}
          </datalist>
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Amount (₹) *
          <input
            className="mt-1 w-32 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Date
          <input type="date" className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={paidDate} onChange={(e) => setPaidDate(e.target.value)} />
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Description
          <input className="mt-1 w-40 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="optional" />
        </label>
        {/* Paid toggle */}
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-zinc-600">Status</span>
          <button
            type="button"
            onClick={() => setIsPaid((v) => !v)}
            className={`mt-1 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
              isPaid
                ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'
                : 'bg-amber-100 text-amber-800 hover:bg-amber-200'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${isPaid ? 'bg-emerald-500' : 'bg-amber-500'}`} />
            {isPaid ? 'Paid' : 'Upcoming'}
          </button>
        </div>
        <button
          type="submit"
          disabled={isPending}
          className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50 self-end"
        >
          + Add
        </button>
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </form>
  )
}

function paiseTo2dp(paise: number | null | undefined): string {
  if (paise == null) return ''
  return (paise / 100).toFixed(2)
}

// ── Helpers ────────────────────────────────────────────────────────────────

/** Indian FY for a given date: April = start of FY. Returns e.g. "2025-26". */
function fyOf(d: Date): string {
  const y = d.getFullYear()
  const m = d.getMonth() // 0-based; 3 = April
  return m >= 3 ? `${y}-${String(y + 1).slice(2)}` : `${y - 1}-${String(y).slice(2)}`
}

/** Derive month_index of "now" relative to a start date (1-based, clamped to schedule). */
function emispaidFromStartDate(startDate: string, totalRows: number): number {
  const start = new Date(startDate)
  const now = new Date()
  const months = (now.getFullYear() - start.getFullYear()) * 12 + (now.getMonth() - start.getMonth())
  return Math.min(Math.max(months, 0), totalRows)
}

// ── LinkedLoanCard ──────────────────────────────────────────────────────────

function LinkedLoanCard({
  loan,
  debt,
  onUnlink,
}: {
  loan: AssetLoanOut
  debt: DebtOut | null
  onUnlink: () => void
}) {
  const [expanded, setExpanded] = useState(false)

  const amort = useQuery({
    queryKey: ['amortization', loan.debt_id],
    queryFn: () => fetchDebtAmortization(loan.debt_id),
    enabled: expanded,
  })

  const rows: AmortizationRow[] = amort.data?.rows ?? []
  const totalEMIs = rows.length

  // Prefer first_emi_date for accuracy; fall back to start_date
  const emisRefDate = debt?.first_emi_date ?? debt?.start_date ?? null
  const emisPaid = emisRefDate && totalEMIs > 0
    ? emispaidFromStartDate(emisRefDate, totalEMIs)
    : 0

  const totalInterest = rows.reduce((s, r) => s + r.interest_paise, 0)
  const interestPaid = rows.slice(0, emisPaid).reduce((s, r) => s + r.interest_paise, 0)
  const interestRemaining = totalInterest - interestPaid

  const principalOrig = debt?.original_amount_paise ?? 0
  const principalRemaining = debt?.current_balance_paise ?? 0
  const principalPaid = principalOrig - principalRemaining

  const emi = debt?.emi_paise ?? loan.final_emi_paise ?? 0
  const rate = debt?.rate_percent ?? 0
  const monthlyRate = rate / 100 / 12

  // Current EMI split (next scheduled payment)
  const nextRow = rows[emisPaid] ?? null
  const currentInterestComp = nextRow?.interest_paise ?? (principalRemaining * monthlyRate)
  const currentPrincipalComp = emi > 0 ? Math.max(0, emi - currentInterestComp) : 0
  const interestBleedPct = emi > 0 ? Math.round((currentInterestComp / emi) * 100) : 0

  // Total cost of borrowing
  const totalCost = principalOrig + totalInterest
  const interestMultiple = principalOrig > 0 ? totalInterest / principalOrig : 0

  // Loan closure date
  const closureDate = (() => {
    if (!debt?.start_date || totalEMIs === 0) return null
    const start = new Date(debt.start_date)
    start.setMonth(start.getMonth() + totalEMIs)
    return start.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
  })()

  // Section 24(b) interest this FY
  const todayFy = fyOf(new Date())
  const fyInterest = (() => {
    if (!debt?.start_date || rows.length === 0) return null
    const start = new Date(debt.start_date)
    let total = 0
    rows.forEach((r, i) => {
      const d = new Date(start)
      d.setMonth(d.getMonth() + i + 1)
      if (fyOf(d) === todayFy) total += r.interest_paise
    })
    return total
  })()

  const progressPct = totalEMIs > 0 ? Math.round((emisPaid / totalEMIs) * 100) : 0

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm">
      {/* Header row */}
      <div className="flex items-center justify-between gap-4 px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="text-base font-semibold text-zinc-900">{loan.debt_name || '—'}</span>
          {debt && (
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600 tabular-nums">
              {rate}% • {debt.type}
            </span>
          )}
          {debt?.status === 'closed' && (
            <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">Closed</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded-lg border border-zinc-200 px-3 py-1 text-xs font-medium text-zinc-600 hover:bg-zinc-50"
          >
            {expanded ? 'Hide analytics ▲' : 'Show analytics ▼'}
          </button>
          <button
            type="button"
            onClick={onUnlink}
            className="rounded px-2 py-0.5 text-xs text-red-500 hover:bg-red-50"
          >
            Unlink
          </button>
        </div>
      </div>

      {/* Always-visible quick stats */}
      <div className="grid grid-cols-2 gap-px border-t border-zinc-100 bg-zinc-100 sm:grid-cols-4 lg:grid-cols-6">
        {[
          { label: 'Sanctioned', value: loan.sanctioned_amount_paise != null ? formatPaiseCompact(loan.sanctioned_amount_paise) : '—' },
          { label: 'Disbursed', value: loan.disbursed_amount_paise != null ? formatPaiseCompact(loan.disbursed_amount_paise) : '—' },
          { label: 'To disburse', value: loan.remaining_to_disburse_paise != null ? formatPaiseCompact(loan.remaining_to_disburse_paise) : '—' },
          { label: 'Pre-EMI /mo', value: loan.pre_emi_paise != null ? formatPaise(loan.pre_emi_paise) : '—' },
          { label: 'Final EMI /mo', value: emi > 0 ? formatPaise(emi) : '—' },
          { label: 'Outstanding', value: principalRemaining > 0 ? formatPaiseCompact(principalRemaining) : '—' },
        ].map((s) => (
          <div key={s.label} className="bg-white px-4 py-3">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{s.label}</p>
            <p className="mt-0.5 text-sm font-semibold tabular-nums text-zinc-900">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Expanded analytics */}
      {expanded && (
        <div className="border-t border-zinc-100 p-5 space-y-6">
          <DisbursalSchedule debtId={loan.debt_id} debt={debt} />
          {amort.isPending ? (
            <p className="text-sm text-zinc-500">Loading amortization…</p>
          ) : amort.isError ? (
            <p className="text-sm text-red-600">Could not load amortization data.</p>
          ) : totalEMIs === 0 ? (
            <p className="text-sm text-zinc-500">No amortization data — make sure rate % and EMI are set on this loan in the Debt section.</p>
          ) : (
            <>
              {/* EMI progress */}
              <div>
                <div className="mb-1.5 flex items-center justify-between text-sm">
                  <span className="font-medium text-zinc-700">
                    {emisPaid} of {totalEMIs} EMIs paid
                    <span className="ml-2 text-zinc-400">({progressPct}% complete)</span>
                  </span>
                  {closureDate && (
                    <span className="text-xs text-zinc-500">Closes {closureDate}</span>
                  )}
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-zinc-100">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <div className="mt-1 flex justify-between text-[11px] text-zinc-400">
                  <span>{totalEMIs - emisPaid} EMIs remaining</span>
                  <span>{Math.floor((totalEMIs - emisPaid) / 12)}y {(totalEMIs - emisPaid) % 12}m left</span>
                </div>
              </div>

              {/* Principal & Interest grid */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { label: 'Principal paid', value: formatPaiseCompact(principalPaid), sub: `of ${formatPaiseCompact(principalOrig)}`, color: 'emerald' },
                  { label: 'Principal left', value: formatPaiseCompact(principalRemaining), sub: `${Math.round((principalRemaining / principalOrig) * 100)}% remaining`, color: 'zinc' },
                  { label: 'Interest paid', value: formatPaiseCompact(interestPaid), sub: `so far`, color: 'amber' },
                  { label: 'Interest left', value: formatPaiseCompact(interestRemaining), sub: `still to pay`, color: 'red' },
                ].map((k) => (
                  <div key={k.label} className={`rounded-xl border p-3 ${k.color === 'red' ? 'border-red-100 bg-red-50' : k.color === 'amber' ? 'border-amber-100 bg-amber-50' : k.color === 'emerald' ? 'border-emerald-100 bg-emerald-50' : 'border-zinc-100 bg-zinc-50'}`}>
                    <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{k.label}</p>
                    <p className={`mt-0.5 text-lg font-bold tabular-nums ${k.color === 'red' ? 'text-red-700' : k.color === 'amber' ? 'text-amber-700' : k.color === 'emerald' ? 'text-emerald-700' : 'text-zinc-800'}`}>{k.value}</p>
                    <p className="mt-0.5 text-[11px] text-zinc-400">{k.sub}</p>
                  </div>
                ))}
              </div>

              {/* Total cost of borrowing */}
              <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-2">Total cost of borrowing</p>
                <div className="flex flex-wrap gap-6 items-baseline">
                  <div>
                    <span className="text-2xl font-bold tabular-nums text-zinc-900">{formatPaiseCompact(totalCost)}</span>
                    <span className="ml-2 text-sm text-zinc-400">total outgo</span>
                  </div>
                  <div>
                    <span className="text-xl font-bold tabular-nums text-red-600">{formatPaiseCompact(totalInterest)}</span>
                    <span className="ml-2 text-sm text-zinc-400">total interest ({(interestMultiple * 100).toFixed(0)}% of principal)</span>
                  </div>
                </div>
                <p className="mt-1.5 text-xs text-zinc-400">
                  For every ₹100 borrowed, you pay ₹{(100 + interestMultiple * 100).toFixed(0)} total.
                </p>
              </div>

              {/* Current EMI split — the bleed meter */}
              {emi > 0 && (
                <div className="rounded-xl border border-zinc-200 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500 mb-3">This month's EMI breakdown</p>
                  <div className="flex items-center gap-4 mb-3">
                    <span className="text-2xl font-bold tabular-nums text-zinc-900">{formatPaise(emi)}</span>
                    <span className="text-sm text-zinc-400">=</span>
                    <span className="text-base font-semibold text-emerald-700 tabular-nums">{formatPaise(Math.round(currentPrincipalComp))} principal</span>
                    <span className="text-sm text-zinc-400">+</span>
                    <span className="text-base font-semibold text-red-600 tabular-nums">{formatPaise(Math.round(currentInterestComp))} interest</span>
                  </div>
                  {/* Bleed bar */}
                  <div className="h-3 overflow-hidden rounded-full bg-emerald-100 flex">
                    <div
                      className="h-full bg-emerald-500 rounded-l-full transition-all"
                      style={{ width: `${100 - interestBleedPct}%` }}
                    />
                    <div
                      className="h-full bg-red-400 rounded-r-full transition-all"
                      style={{ width: `${interestBleedPct}%` }}
                    />
                  </div>
                  <div className="mt-1.5 flex justify-between text-xs">
                    <span className="text-emerald-600">{100 - interestBleedPct}% goes to principal</span>
                    <span className={interestBleedPct > 70 ? 'font-semibold text-red-600' : 'text-zinc-500'}>
                      {interestBleedPct}% goes to interest{interestBleedPct > 70 ? ' 🔴' : ''}
                    </span>
                  </div>
                </div>
              )}

              {/* Section 24(b) — FY interest tracker */}
              {fyInterest !== null && (
                <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-blue-600 mb-1">Section 24(b) — Home loan interest deduction</p>
                  <div className="flex items-baseline gap-3">
                    <span className="text-xl font-bold tabular-nums text-blue-800">{formatPaiseCompact(fyInterest)}</span>
                    <span className="text-sm text-blue-600">interest paid in FY {todayFy}</span>
                  </div>
                  <p className="mt-1 text-xs text-blue-500">
                    {fyInterest >= 200_000_00
                      ? `₹2L limit maxed ✓ — deductible: ₹2,00,000`
                      : `Deductible: ${formatPaise(fyInterest)} (limit ₹2L, ${formatPaise(Math.max(0, 200_000_00 - fyInterest))} unused)`}
                  </p>
                </div>
              )}

              {/* Prepayment calculator moved to Debt page — use Analytics ▼ on the loan there */}
              <div className="rounded-xl border border-zinc-100 bg-zinc-50 px-4 py-3">
                <p className="text-xs text-zinc-500">
                  For prepayment scenarios, open the <strong>Debt</strong> page → click <em>Analytics ▼</em> on this loan → Prepayment calculator.
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function AddLoanForm({
  debtOptions,
  onAdd,
  isPending,
  error,
}: {
  debtOptions: DebtOut[]
  onAdd: (body: Parameters<typeof postAssetLoan>[1]) => void
  isPending: boolean
  error: string | null
}) {
  const [debtId, setDebtId] = useState('')
  const [sanctioned, setSanctioned] = useState('')
  const [disbursed, setDisbursed] = useState('')
  const [preEmi, setPreEmi] = useState('')
  const [finalEmi, setFinalEmi] = useState('')
  const [notes, setNotes] = useState('')

  // When a debt is selected, auto-fill from its stored details
  const handleDebtChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const id = e.target.value
    setDebtId(id)
    if (!id) {
      setSanctioned('')
      setFinalEmi('')
      return
    }
    const debt = debtOptions.find((d) => d.id === Number(id))
    if (debt) {
      if (debt.original_amount_paise != null) setSanctioned(paiseTo2dp(debt.original_amount_paise))
      if (debt.emi_paise != null) setFinalEmi(paiseTo2dp(debt.emi_paise))
    }
  }

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    const did = Number.parseInt(debtId, 10)
    if (Number.isNaN(did)) return
    onAdd({
      debt_id: did,
      sanctioned_amount_paise: sanctioned.trim() ? rupeesToPaise(sanctioned) : null,
      disbursed_amount_paise: disbursed.trim() ? rupeesToPaise(disbursed) : null,
      pre_emi_paise: preEmi.trim() ? rupeesToPaise(preEmi) : null,
      final_emi_paise: finalEmi.trim() ? rupeesToPaise(finalEmi) : null,
      notes: notes.trim() || null,
    })
    setDebtId('')
    setSanctioned('')
    setDisbursed('')
    setPreEmi('')
    setFinalEmi('')
    setNotes('')
  }

  if (debtOptions.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        No loans available. <Link to="/debt" className="text-emerald-700 underline">Add a loan first</Link>.
      </p>
    )
  }

  return (
    <form onSubmit={handleAdd} className="flex flex-wrap items-end gap-2">
      <label className="text-xs font-medium text-zinc-600">
        Link loan
        <select
          className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm"
          value={debtId}
          onChange={handleDebtChange}
          required
        >
          <option value="">Select loan…</option>
          {debtOptions.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Sanctioned (₹)
        <input className="mt-1 w-32 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={sanctioned} onChange={(e) => setSanctioned(e.target.value)} placeholder="auto-filled" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Disbursed so far (₹)
        <input className="mt-1 w-32 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={disbursed} onChange={(e) => setDisbursed(e.target.value)} placeholder="optional" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Pre-EMI (₹/mo)
        <input className="mt-1 w-28 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={preEmi} onChange={(e) => setPreEmi(e.target.value)} placeholder="optional" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Final EMI (₹/mo)
        <input className="mt-1 w-28 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums" inputMode="decimal" value={finalEmi} onChange={(e) => setFinalEmi(e.target.value)} placeholder="auto-filled" />
      </label>
      <label className="text-xs font-medium text-zinc-600">
        Notes
        <input className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <button
        type="submit"
        disabled={isPending}
        className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
      >
        + Link loan
      </button>
      {error ? <p className="w-full text-sm text-red-600">{error}</p> : null}
    </form>
  )
}

function paymentToUpdateBody(
  p: AssetPaymentOut,
  patch: Partial<Pick<AssetPaymentBody, 'fund_source'>> = {},
): AssetPaymentBody {
  const fs = patch.fund_source ?? p.fund_source
  const { cash, loan, total } = resolvedSplitPaise(p)
  if (p.is_paid) {
    const pd = p.paid_date ?? p.payment_date.slice(0, 10)
    return {
      milestone: p.milestone ?? '',
      amount_cash_paise: cash,
      amount_loan_paise: loan,
      amount_paise: total,
      is_paid: true,
      paid_date: pd,
      payment_date: pd,
      due_date: p.due_date,
      fund_source: fs,
      reference_number: p.reference_number,
      notes: p.notes,
    }
  }
  const dd = p.due_date ?? p.payment_date.slice(0, 10)
  return {
    milestone: p.milestone ?? '',
    amount_cash_paise: cash,
    amount_loan_paise: loan,
    amount_paise: total,
    is_paid: false,
    due_date: dd,
    fund_source: fs,
    reference_number: p.reference_number,
    notes: p.notes,
  }
}

function FundSourceToggle({
  value,
  disabled,
  onChange,
}: {
  value: 'cash' | 'bank_loan'
  disabled?: boolean
  onChange: (v: 'cash' | 'bank_loan') => void
}) {
  return (
    <div
      className="inline-flex rounded-full border border-zinc-200 bg-white p-0.5 text-[11px] font-semibold"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
    >
      <button
        type="button"
        disabled={disabled}
        className={`rounded-full px-2 py-0.5 transition-colors ${
          value === 'cash' ? 'bg-emerald-100 text-emerald-800' : 'text-zinc-500 hover:text-zinc-800'
        }`}
        onClick={() => onChange('cash')}
      >
        Cash
      </button>
      <button
        type="button"
        disabled={disabled}
        className={`rounded-full px-2 py-0.5 transition-colors ${
          value === 'bank_loan' ? 'bg-emerald-100 text-emerald-800' : 'text-zinc-500 hover:text-zinc-800'
        }`}
        onClick={() => onChange('bank_loan')}
      >
        Loan
      </button>
    </div>
  )
}

function PaymentMilestonesTable({
  payments,
  onAdd,
  onUpdate,
  onDelete,
  addPending,
  updatePending,
  addError,
  updateError,
  totalPaidPaise,
  totalUpcomingPaise,
}: {
  payments: AssetPaymentOut[]
  onAdd: (body: AssetPaymentBody) => void
  onUpdate: (paymentId: number, body: AssetPaymentBody) => void
  onDelete: (paymentId: number) => void
  addPending: boolean
  updatePending: boolean
  addError: string | null
  updateError: string | null
  totalPaidPaise: number
  totalUpcomingPaise: number
}) {
  const paidRows = payments.filter((p) => p.is_paid)
  const upcomingRows = payments.filter((p) => !p.is_paid)
  const paidCash = paidRows.reduce((s, p) => s + resolvedSplitPaise(p).cash, 0)
  const paidLoan = paidRows.reduce((s, p) => s + resolvedSplitPaise(p).loan, 0)
  const paidTotal = paidRows.reduce((s, p) => s + resolvedSplitPaise(p).total, 0)
  const upcomingCash = upcomingRows.reduce((s, p) => s + resolvedSplitPaise(p).cash, 0)
  const upcomingLoan = upcomingRows.reduce((s, p) => s + resolvedSplitPaise(p).loan, 0)
  const upcomingTotal = upcomingRows.reduce((s, p) => s + resolvedSplitPaise(p).total, 0)

  return (
    <Panel variant="table" padding={false}>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-600">
          <tr>
            <th className="px-4 py-2.5">Milestone</th>
            <th className="px-4 py-2.5 text-right">Self-funded</th>
            <th className="px-4 py-2.5 text-right">Loan</th>
            <th className="px-4 py-2.5 text-right">Total</th>
            <th className="px-4 py-2.5">Source</th>
            <th className="px-4 py-2.5">Due date</th>
            <th className="px-4 py-2.5">Paid date</th>
            <th className="px-4 py-2.5">Status</th>
            <th className="px-4 py-2.5">Reference</th>
            <th className="px-4 py-2.5">Notes</th>
            <th className="px-4 py-2.5" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {payments.map((p) => (
            <PaymentMilestoneRow
              key={p.id}
              payment={p}
              onUpdate={onUpdate}
              onDelete={onDelete}
              busy={updatePending}
            />
          ))}
          {payments.length === 0 ? (
            <tr>
              <td colSpan={11} className="px-4 py-4 text-center text-zinc-500">
                No payment milestones yet
              </td>
            </tr>
          ) : null}
        </tbody>
        <tfoot className="border-t-2 border-zinc-300 bg-zinc-50">
          <tr>
            <td className="px-4 py-2 text-xs font-medium text-zinc-600">Paid so far</td>
            <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-emerald-700">
              {formatPaise(paidCash)}
            </td>
            <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-emerald-700">
              {formatPaise(paidLoan)}
            </td>
            <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-emerald-700">
              {formatPaise(paidTotal)}
            </td>
            <td colSpan={7} />
          </tr>
          {upcomingTotal > 0 ? (
            <tr>
              <td className="px-4 py-2 text-xs font-medium text-zinc-600">Upcoming</td>
              <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-amber-700">
                {formatPaise(upcomingCash)}
              </td>
              <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-amber-700">
                {formatPaise(upcomingLoan)}
              </td>
              <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums text-amber-700">
                {formatPaise(upcomingTotal)}
              </td>
              <td colSpan={7} />
            </tr>
          ) : null}
          <tr className="border-t border-zinc-200">
            <td className="px-4 py-2.5 text-sm font-bold text-zinc-800">Total milestones</td>
            <td className="px-4 py-2.5 text-right text-sm font-bold tabular-nums text-zinc-900">
              {formatPaise(paidCash + upcomingCash)}
            </td>
            <td className="px-4 py-2.5 text-right text-sm font-bold tabular-nums text-zinc-900">
              {formatPaise(paidLoan + upcomingLoan)}
            </td>
            <td className="px-4 py-2.5 text-right text-sm font-bold tabular-nums text-zinc-900">
              {formatPaise(paidTotal + upcomingTotal)}
            </td>
            <td colSpan={7} />
          </tr>
        </tfoot>
      </table>
      <div className="border-t border-zinc-100 px-4 py-3">
        <AddPaymentForm onAdd={onAdd} isPending={addPending} error={addError} />
        {updateError ? <p className="mt-2 text-sm text-red-600">{updateError}</p> : null}
        <p className="mt-1 text-xs text-zinc-500">
          KPI summary: paid {formatPaise(totalPaidPaise)}
          {totalUpcomingPaise > 0 ? ` · upcoming ${formatPaise(totalUpcomingPaise)}` : ''}
        </p>
      </div>
    </Panel>
  )
}

function PaymentMilestoneRow({
  payment,
  onUpdate,
  onDelete,
  busy,
}: {
  payment: AssetPaymentOut
  onUpdate: (paymentId: number, body: AssetPaymentBody) => void
  onDelete: (paymentId: number) => void
  busy: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [milestone, setMilestone] = useState(payment.milestone ?? '')
  const [amountCash, setAmountCash] = useState(() => paiseToRupees(resolvedSplitPaise(payment).cash))
  const [amountLoan, setAmountLoan] = useState(() => paiseToRupees(resolvedSplitPaise(payment).loan))
  const [dueDate, setDueDate] = useState(payment.due_date ?? '')
  const [paidDate, setPaidDate] = useState(payment.paid_date ?? '')
  const [isPaid, setIsPaid] = useState(payment.is_paid)
  const [refNumber, setRefNumber] = useState(payment.reference_number ?? '')
  const [notes, setNotes] = useState(payment.notes ?? '')
  const [fundSource, setFundSource] = useState<'cash' | 'bank_loan'>(payment.fund_source)

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- hydrate payment row editor */
    setMilestone(payment.milestone ?? '')
    const sp = resolvedSplitPaise(payment)
    setAmountCash(paiseToRupees(sp.cash))
    setAmountLoan(paiseToRupees(sp.loan))
    setDueDate(payment.due_date ?? '')
    setPaidDate(payment.paid_date ?? '')
    setIsPaid(payment.is_paid)
    setRefNumber(payment.reference_number ?? '')
    setNotes(payment.notes ?? '')
    setFundSource(payment.fund_source)
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [payment])

  const editTotalPaise =
    (rupeesToPaiseOrZero(amountCash) ?? 0) + (rupeesToPaiseOrZero(amountLoan) ?? 0)

  const buildBody = (): AssetPaymentBody | null => {
    const cashP = rupeesToPaiseOrZero(amountCash)
    const loanP = rupeesToPaiseOrZero(amountLoan)
    if (cashP == null || loanP == null || !milestone.trim()) return null
    const total = cashP + loanP
    if (total <= 0) return null
    if (isPaid) {
      if (!paidDate.trim()) return null
      return {
        milestone: milestone.trim(),
        amount_cash_paise: cashP,
        amount_loan_paise: loanP,
        amount_paise: total,
        is_paid: true,
        paid_date: paidDate.trim(),
        payment_date: paidDate.trim(),
        due_date: dueDate.trim() || null,
        fund_source: fundSource,
        reference_number: refNumber.trim() || null,
        notes: notes.trim() || null,
      }
    }
    if (!dueDate.trim()) return null
    return {
      milestone: milestone.trim(),
      amount_cash_paise: cashP,
      amount_loan_paise: loanP,
      amount_paise: total,
      is_paid: false,
      due_date: dueDate.trim(),
      paid_date: null,
      payment_date: null,
      fund_source: fundSource,
      reference_number: refNumber.trim() || null,
      notes: notes.trim() || null,
    }
  }

  const handleSave = () => {
    const body = buildBody()
    if (!body) return
    onUpdate(payment.id, body)
    setEditing(false)
  }

  const handleCancel = () => {
    setMilestone(payment.milestone ?? '')
    const sp = resolvedSplitPaise(payment)
    setAmountCash(paiseToRupees(sp.cash))
    setAmountLoan(paiseToRupees(sp.loan))
    setDueDate(payment.due_date ?? '')
    setPaidDate(payment.paid_date ?? '')
    setIsPaid(payment.is_paid)
    setRefNumber(payment.reference_number ?? '')
    setNotes(payment.notes ?? '')
    setFundSource(payment.fund_source)
    setEditing(false)
  }

  const cellCls = 'px-2 py-1.5'
  const editInput = 'w-full rounded border border-emerald-400 bg-white px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500'
  const amtCls = (paid: boolean) =>
    `px-4 py-2.5 text-right tabular-nums font-semibold ${paid ? 'text-zinc-900' : 'text-amber-700'}`

  if (!editing) {
    const sp = resolvedSplitPaise(payment)
    return (
      <tr
        className={`group cursor-pointer text-zinc-800 hover:bg-zinc-50 ${!payment.is_paid ? 'opacity-80' : ''}`}
        onClick={() => setEditing(true)}
      >
        <td className="px-4 py-2.5 font-medium">
          {payment.milestone}
          <span className="ml-2 hidden text-[10px] text-zinc-400 group-hover:inline">✎ edit</span>
        </td>
        <td className={amtCls(payment.is_paid)}>{formatPaise(sp.cash)}</td>
        <td className={amtCls(payment.is_paid)}>{formatPaise(sp.loan)}</td>
        <td className={amtCls(payment.is_paid)}>{formatPaise(sp.total)}</td>
        <td className="px-4 py-2.5">
          <FundSourceToggle
            value={payment.fund_source}
            disabled={busy}
            onChange={(v) => {
              if (v === payment.fund_source) return
              onUpdate(payment.id, paymentToUpdateBody(payment, { fund_source: v }))
            }}
          />
        </td>
        <td className="px-4 py-2.5 text-xs text-zinc-600">{payment.due_date ?? '—'}</td>
        <td className="px-4 py-2.5 text-xs text-zinc-600">{payment.paid_date ?? '—'}</td>
        <td className="px-4 py-2.5">
          {payment.is_paid ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
              ✓ Paid
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-700">
              ⏳ Upcoming
            </span>
          )}
        </td>
        <td className="px-4 py-2.5 text-xs text-zinc-500">{payment.reference_number ?? '—'}</td>
        <td className="px-4 py-2.5 text-xs text-zinc-400">{payment.notes ?? ''}</td>
        <td className="px-4 py-2.5 text-right">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onDelete(payment.id)
            }}
            className="rounded px-2 py-0.5 text-xs text-red-400 opacity-0 hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
          >
            Delete
          </button>
        </td>
      </tr>
    )
  }

  return (
    <tr className="bg-emerald-50 ring-1 ring-inset ring-emerald-200">
      <td className={cellCls}>
        <input
          className={editInput}
          value={milestone}
          onChange={(e) => setMilestone(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSave()
            if (e.key === 'Escape') handleCancel()
          }}
        />
      </td>
      <td className={cellCls}>
        <input
          className={`${editInput} text-right tabular-nums`}
          inputMode="decimal"
          value={amountCash}
          onChange={(e) => setAmountCash(e.target.value)}
          placeholder="0"
        />
      </td>
      <td className={cellCls}>
        <input
          className={`${editInput} text-right tabular-nums`}
          inputMode="decimal"
          value={amountLoan}
          onChange={(e) => setAmountLoan(e.target.value)}
          placeholder="0"
        />
      </td>
      <td className={`${cellCls} text-right tabular-nums text-sm font-semibold text-zinc-800`}>
        {formatPaise(editTotalPaise)}
      </td>
      <td className={cellCls}>
        <FundSourceToggle value={fundSource} disabled={busy} onChange={setFundSource} />
      </td>
      <td className={cellCls}>
        <input type="date" className={editInput} value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
      </td>
      <td className={cellCls}>
        <input type="date" className={editInput} value={paidDate} onChange={(e) => setPaidDate(e.target.value)} />
      </td>
      <td className={cellCls}>
        <button
          type="button"
          onClick={() => setIsPaid((v) => !v)}
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
            isPaid
              ? 'bg-emerald-200 text-emerald-800 hover:bg-emerald-300'
              : 'bg-amber-200 text-amber-800 hover:bg-amber-300'
          }`}
        >
          <span className={`h-2 w-2 rounded-full ${isPaid ? 'bg-emerald-600' : 'bg-amber-500'}`} />
          {isPaid ? 'Paid' : 'Upcoming'}
        </button>
      </td>
      <td className={cellCls}>
        <input className={editInput} value={refNumber} onChange={(e) => setRefNumber(e.target.value)} />
      </td>
      <td className={cellCls}>
        <input className={editInput} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </td>
      <td className={`${cellCls} text-right`}>
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            disabled={busy}
            onClick={handleSave}
            className="rounded bg-emerald-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            Save
          </button>
          <button
            type="button"
            onClick={handleCancel}
            className="rounded border border-zinc-300 px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100"
          >
            ✕
          </button>
        </div>
      </td>
    </tr>
  )
}

function AddPaymentForm({
  onAdd,
  isPending,
  error,
}: {
  onAdd: (body: AssetPaymentBody) => void
  isPending: boolean
  error: string | null
}) {
  const [milestone, setMilestone] = useState('')
  const [amountCash, setAmountCash] = useState('')
  const [amountLoan, setAmountLoan] = useState('')
  const [fundSource, setFundSource] = useState<'cash' | 'bank_loan'>('cash')
  const [dueDate, setDueDate] = useState('')
  const [paidDate, setPaidDate] = useState('')
  const [isPaid, setIsPaid] = useState(true)
  const [refNumber, setRefNumber] = useState('')
  const [notes, setNotes] = useState('')

  const cAdd = rupeesToPaiseOrZero(amountCash)
  const lAdd = rupeesToPaiseOrZero(amountLoan)
  const addTotalPaise = (cAdd ?? 0) + (lAdd ?? 0)

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault()
    const cashP = rupeesToPaiseOrZero(amountCash)
    const loanP = rupeesToPaiseOrZero(amountLoan)
    if (cashP == null || loanP == null || !milestone.trim()) return
    const total = cashP + loanP
    if (total <= 0) return
    if (isPaid) {
      if (!paidDate.trim()) return
      onAdd({
        milestone: milestone.trim(),
        amount_cash_paise: cashP,
        amount_loan_paise: loanP,
        amount_paise: total,
        is_paid: true,
        paid_date: paidDate.trim(),
        payment_date: paidDate.trim(),
        due_date: dueDate.trim() || null,
        fund_source: fundSource,
        reference_number: refNumber.trim() || null,
        notes: notes.trim() || null,
      })
    } else {
      if (!dueDate.trim()) return
      onAdd({
        milestone: milestone.trim(),
        amount_cash_paise: cashP,
        amount_loan_paise: loanP,
        amount_paise: total,
        is_paid: false,
        due_date: dueDate.trim(),
        fund_source: fundSource,
        reference_number: refNumber.trim() || null,
        notes: notes.trim() || null,
      })
    }
    setMilestone('')
    setAmountCash('')
    setAmountLoan('')
    setFundSource('cash')
    setDueDate('')
    setPaidDate('')
    setIsPaid(true)
    setRefNumber('')
    setNotes('')
  }

  return (
    <form onSubmit={handleAdd} className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Add milestone</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs font-medium text-zinc-600">
          Milestone *
          <input
            className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm w-44"
            value={milestone}
            onChange={(e) => setMilestone(e.target.value)}
            placeholder="e.g. 20% slab"
            required
          />
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Self-funded (₹)
          <input
            className="mt-1 w-24 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={amountCash}
            onChange={(e) => setAmountCash(e.target.value)}
            placeholder="0"
          />
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Loan (₹)
          <input
            className="mt-1 w-24 rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
            inputMode="decimal"
            value={amountLoan}
            onChange={(e) => setAmountLoan(e.target.value)}
            placeholder="0"
          />
        </label>
        <div className="flex flex-col gap-0.5">
          <span className="text-xs font-medium text-zinc-600">Total</span>
          <span className="mt-1 rounded border border-zinc-100 bg-zinc-50 px-2 py-1.5 text-right text-sm font-semibold tabular-nums text-zinc-900">
            {formatPaise(addTotalPaise)}
          </span>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-zinc-600">Source</span>
          <div className="mt-1">
            <FundSourceToggle value={fundSource} disabled={isPending} onChange={setFundSource} />
          </div>
        </div>
        <label className="text-xs font-medium text-zinc-600">
          Due date
          <input
            type="date"
            className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
          />
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Paid date
          <input
            type="date"
            className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm"
            value={paidDate}
            onChange={(e) => setPaidDate(e.target.value)}
          />
        </label>
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-zinc-600">Status</span>
          <button
            type="button"
            onClick={() => setIsPaid((v) => !v)}
            className={`mt-1 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
              isPaid
                ? 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'
                : 'bg-amber-100 text-amber-800 hover:bg-amber-200'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${isPaid ? 'bg-emerald-500' : 'bg-amber-500'}`} />
            {isPaid ? 'Paid' : 'Upcoming'}
          </button>
        </div>
        <label className="text-xs font-medium text-zinc-600">
          Reference
          <input className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm" value={refNumber} onChange={(e) => setRefNumber(e.target.value)} />
        </label>
        <label className="text-xs font-medium text-zinc-600">
          Notes
          <input className="mt-1 rounded border border-zinc-200 px-2 py-1.5 text-sm w-40" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <button
          type="submit"
          disabled={isPending}
          className="rounded-lg bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50 self-end"
        >
          + Add
        </button>
      </div>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </form>
  )
}

// ── DisbursalSchedule ─────────────────────────────────────────────────────────

function DisbursalSchedule({
  debtId,
  debt,
}: {
  debtId: number
  debt: DebtOut | null
}) {
  const qc = useQueryClient()
  const [date, setDate] = useState('')
  const [amount, setAmount] = useState('')
  const [disbNotes, setDisbNotes] = useState('')

  const disbursals = useQuery({
    queryKey: ['disbursals', debtId],
    queryFn: () => fetchDisbursals(debtId),
  })

  const addDisbursal = useMutation({
    mutationFn: () =>
      postDisbursal(debtId, {
        disbursal_date: date,
        amount_paise: Math.round(Number.parseFloat(amount.replace(/,/g, '')) * 100),
        notes: disbNotes.trim() || null,
      }),
    onSuccess: () => {
      setDate('')
      setAmount('')
      setDisbNotes('')
      void qc.invalidateQueries({ queryKey: ['disbursals', debtId] })
      void qc.invalidateQueries({ queryKey: ['amortization', debtId] })
    },
  })

  const removeDisbursal = useMutation({
    mutationFn: (disbursalId: number) => deleteDisbursal(debtId, disbursalId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['disbursals', debtId] })
      void qc.invalidateQueries({ queryKey: ['amortization', debtId] })
    },
  })

  const items: LoanDisbursalOut[] = disbursals.data ?? []
  const isHomeLoan =
    debt?.type?.toLowerCase().includes('home') ||
    debt?.type?.toLowerCase().includes('property') ||
    debt?.type?.toLowerCase().includes('mortgage')

  // Don't render for non-home loans that have no disbursals
  if (!isHomeLoan && items.length === 0) return null

  const sanctioned = debt?.original_amount_paise ?? null
  const totalDisbursed = items.reduce((s, d) => s + d.amount_paise, 0)
  const remaining = sanctioned != null ? sanctioned - totalDisbursed : null

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
          Disbursal schedule
        </p>
        {sanctioned != null && (
          <span className="text-xs text-amber-600 tabular-nums">
            {formatPaiseCompact(totalDisbursed)} of {formatPaiseCompact(sanctioned)}
            {remaining != null && remaining > 0 && ` · ${formatPaiseCompact(remaining)} pending`}
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <p className="text-xs text-amber-600">No disbursals recorded. Add the first tranche below.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-amber-200 text-amber-700">
                <th className="pb-1 text-left font-semibold">Date</th>
                <th className="pb-1 text-right font-semibold">Tranche</th>
                <th className="pb-1 text-right font-semibold">Cumulative</th>
                <th className="pb-1 text-right font-semibold">Pre-EMI /mo</th>
                <th className="pb-1 pl-3 text-left font-semibold">Notes</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((d) => {
                const rate = debt?.rate_percent ?? 0
                const preEmi = rate > 0 ? Math.round(d.cumulative_paise * (rate / 100 / 12)) : null
                return (
                  <tr key={d.id} className="border-b border-amber-100">
                    <td className="py-1.5 font-medium">{d.disbursal_date}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatPaiseCompact(d.amount_paise)}</td>
                    <td className="py-1.5 text-right tabular-nums font-semibold">{formatPaiseCompact(d.cumulative_paise)}</td>
                    <td className="py-1.5 text-right tabular-nums text-amber-700">
                      {preEmi != null ? formatPaise(preEmi) : '—'}
                    </td>
                    <td className="py-1.5 pl-3 text-zinc-500">{d.notes ?? '—'}</td>
                    <td className="py-1.5 text-right">
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm('Remove this disbursal tranche?')) {
                            removeDisbursal.mutate(d.id)
                          }
                        }}
                        className="text-red-400 hover:text-red-600"
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Progress bar */}
      {sanctioned != null && sanctioned > 0 && (
        <div>
          <div className="h-2 overflow-hidden rounded-full bg-amber-200">
            <div
              className="h-full rounded-full bg-amber-500 transition-all"
              style={{ width: `${Math.min(100, (totalDisbursed / sanctioned) * 100)}%` }}
            />
          </div>
          <p className="mt-1 text-[11px] text-amber-600">
            {Math.round((totalDisbursed / sanctioned) * 100)}% disbursed
          </p>
        </div>
      )}

      {/* Add tranche form */}
      <form
        className="flex flex-wrap items-end gap-2 border-t border-amber-200 pt-3"
        onSubmit={(e) => {
          e.preventDefault()
          if (!date || !amount) return
          addDisbursal.mutate()
        }}
      >
        <label className="text-[10px] font-semibold uppercase text-amber-700">
          Date
          <input
            type="date"
            required
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="mt-1 block rounded border border-amber-200 bg-white px-2 py-1 text-xs [color-scheme:light]"
          />
        </label>
        <label className="text-[10px] font-semibold uppercase text-amber-700">
          Tranche (₹)
          <input
            required
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="e.g. 1000000"
            className="mt-1 block w-32 rounded border border-amber-200 bg-white px-2 py-1 text-right text-xs tabular-nums"
          />
        </label>
        <label className="text-[10px] font-semibold uppercase text-amber-700">
          Notes
          <input
            value={disbNotes}
            onChange={(e) => setDisbNotes(e.target.value)}
            placeholder="Foundation, Slab 1…"
            className="mt-1 block w-40 rounded border border-amber-200 bg-white px-2 py-1 text-xs"
          />
        </label>
        <button
          type="submit"
          disabled={addDisbursal.isPending}
          className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
        >
          + Add tranche
        </button>
        {addDisbursal.isError && (
          <p className="w-full text-xs text-red-600">{String(addDisbursal.error)}</p>
        )}
      </form>

      {/* Status line */}
      {debt?.full_emi_start_date ? (
        <p className="text-xs text-amber-600">
          Full EMI starts: <strong>{debt.full_emi_start_date}</strong>
          {debt.tenure_months != null && ` · ${debt.tenure_months}m total tenure`}
        </p>
      ) : items.length > 0 ? (
        <p className="text-xs text-amber-500">
          Full EMI start date not set — defaults to last disbursal ({items[items.length - 1].disbursal_date}).
          Set it on the <strong>Debt page</strong> for accurate amortization.
        </p>
      ) : null}
    </div>
  )
}
