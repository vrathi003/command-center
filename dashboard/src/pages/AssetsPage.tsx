import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  deleteAsset,
  fetchAssets,
  fetchAssetSummary,
  postAsset,
} from '@/lib/api'
import { formatPaiseCompact } from '@/lib/format'
import type { AssetOut } from '@/types/api'


const ASSET_TYPES = ['apartment', 'plot', 'commercial', 'vehicle', 'gold', 'other'] as const
const ASSET_STATUSES = ['active', 'sold'] as const

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) return null
  return Math.round(n * 100)
}

function typeBadgeColor(type: string): string {
  switch (type) {
    case 'apartment': return 'bg-blue-100 text-blue-800'
    case 'plot': return 'bg-emerald-100 text-emerald-800'
    case 'commercial': return 'bg-purple-100 text-purple-800'
    case 'vehicle': return 'bg-amber-100 text-amber-800'
    case 'gold': return 'bg-yellow-100 text-yellow-800'
    default: return 'bg-zinc-100 text-zinc-700'
  }
}

function statusBadgeColor(status: string): string {
  return status === 'active'
    ? 'bg-emerald-100 text-emerald-800'
    : 'bg-zinc-200 text-zinc-600'
}

function appreciationColor(pct: number | null): string {
  if (pct == null) return 'text-zinc-500'
  return pct >= 0 ? 'text-emerald-700' : 'text-red-600'
}

export function AssetsPage() {
  const qc = useQueryClient()
  const [showAddModal, setShowAddModal] = useState(false)

  const summary = useQuery({
    queryKey: ['asset-summary'],
    queryFn: fetchAssetSummary,
  })

  const assets = useQuery({
    queryKey: ['assets'],
    queryFn: fetchAssets,
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['assets'] })
    void qc.invalidateQueries({ queryKey: ['asset-summary'] })
    void qc.invalidateQueries({ queryKey: ['net-worth-history'] })
    void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
  }

  const create = useMutation({
    mutationFn: postAsset,
    onSuccess: () => {
      invalidate()
      setShowAddModal(false)
    },
  })

  const remove = useMutation({
    mutationFn: deleteAsset,
    onSuccess: () => invalidate(),
  })

  if (summary.isPending || assets.isPending) return <PageLoading lines={4} />
  if (summary.isError || assets.isError) {
    return (
      <PageError
        title="Could not load assets"
        message={<p className="text-sm">{String(summary.error ?? assets.error)}</p>}
      />
    )
  }

  const s = summary.data
  const list = assets.data

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Wealth"
        title="Assets"
        description="Real estate, vehicles, gold & other physical assets · refreshes every 30s"
      />

      {/* KPI cards */}
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard tone="neutral" label="Total assets" value={String(s.total_assets)} />
        <KpiCard
          tone="neutral"
          label="Current value"
          value={formatPaiseCompact(s.total_current_value_paise)}
        />
        <KpiCard
          tone="neutral"
          label="Purchase price"
          value={formatPaiseCompact(s.total_purchase_price_paise)}
        />
        <KpiCard
          tone={s.overall_appreciation_pct != null && s.overall_appreciation_pct >= 0 ? 'neutral' : 'spending'}
          label="Overall appreciation"
          value={s.overall_appreciation_pct != null ? `${s.overall_appreciation_pct.toFixed(1)}%` : '—'}
        />
      </section>

      {/* Asset list */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <SectionTitle>Your assets</SectionTitle>
          <button
            type="button"
            onClick={() => setShowAddModal(true)}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800"
          >
            + Add asset
          </button>
        </div>

        {list.length === 0 ? (
          <Panel>
            <p className="py-6 text-center text-sm text-zinc-500">
              No assets yet — add one to start tracking your physical wealth.
            </p>
          </Panel>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {list.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                onDelete={() => {
                  if (window.confirm(`Delete asset "${asset.name}"?`)) {
                    remove.mutate(asset.id)
                  }
                }}
              />
            ))}
          </div>
        )}
        {remove.isError ? (
          <p className="mt-2 text-sm text-red-600">{String(remove.error)}</p>
        ) : null}
      </section>

      {/* Add modal */}
      {showAddModal ? (
        <AddAssetModal
          onClose={() => setShowAddModal(false)}
          onCreate={(body) => create.mutate(body)}
          isPending={create.isPending}
          error={create.isError ? String(create.error) : null}
        />
      ) : null}
    </div>
  )
}

function AssetCard({
  asset,
  onDelete,
}: {
  asset: AssetOut
  onDelete: () => void
}) {
  const appreciationPct =
    asset.current_value_paise != null && asset.purchase_price_paise != null && asset.purchase_price_paise > 0
      ? ((asset.current_value_paise - asset.purchase_price_paise) / asset.purchase_price_paise) * 100
      : null

  return (
    <div className="flex flex-col rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            to={`/assets/${asset.id}`}
            className="truncate text-base font-semibold text-zinc-900 hover:text-emerald-700"
          >
            {asset.name}
          </Link>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${typeBadgeColor(asset.type)}`}
            >
              {asset.type}
            </span>
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusBadgeColor(asset.status)}`}
            >
              {asset.status}
            </span>
            {asset.ownership_percent < 100 ? (
              <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
                {asset.ownership_percent}% owned
              </span>
            ) : null}
          </div>
        </div>
        <button
          type="button"
          onClick={onDelete}
          className="shrink-0 rounded px-2 py-1 text-xs text-red-500 hover:bg-red-50"
        >
          Delete
        </button>
      </div>

      <div className="mt-auto grid grid-cols-2 gap-y-2 text-sm">
        <div>
          <p className="text-xs text-zinc-500">Current value</p>
          <p className="font-semibold tabular-nums text-zinc-900">
            {asset.current_value_paise != null ? formatPaiseCompact(asset.current_value_paise) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Purchase price</p>
          <p className="tabular-nums text-zinc-700">
            {asset.purchase_price_paise != null ? formatPaiseCompact(asset.purchase_price_paise) : '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Appreciation</p>
          <p className={`tabular-nums font-medium ${appreciationColor(appreciationPct)}`}>
            {appreciationPct != null ? `${appreciationPct >= 0 ? '+' : ''}${appreciationPct.toFixed(1)}%` : '—'}
          </p>
        </div>
        {asset.purchase_date ? (
          <div>
            <p className="text-xs text-zinc-500">Purchase date</p>
            <p className="text-zinc-700">{asset.purchase_date}</p>
          </div>
        ) : null}
        {asset.co_owner ? (
          <div className="col-span-2">
            <p className="text-xs text-zinc-500">Co-owner</p>
            <p className="text-zinc-700">{asset.co_owner}</p>
          </div>
        ) : null}
      </div>

      <Link
        to={`/assets/${asset.id}`}
        className="mt-3 block rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-center text-xs font-medium text-emerald-800 hover:bg-emerald-100"
      >
        View details &amp; edit
      </Link>
    </div>
  )
}

function AddAssetModal({
  onClose,
  onCreate,
  isPending,
  error,
}: {
  onClose: () => void
  onCreate: (body: Partial<AssetOut>) => void
  isPending: boolean
  error: string | null
}) {
  const [name, setName] = useState('')
  const [type, setType] = useState<string>(ASSET_TYPES[0])
  const [status, setStatus] = useState<string>('active')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [purchasePrice, setPurchasePrice] = useState('')
  const [currentValue, setCurrentValue] = useState('')
  const [ownershipPct, setOwnershipPct] = useState('100')
  const [coOwner, setCoOwner] = useState('')
  const [notes, setNotes] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const pp = purchasePrice.trim() === '' ? null : rupeesToPaise(purchasePrice)
    const cv = currentValue.trim() === '' ? null : rupeesToPaise(currentValue)
    const ownershipNum = Number.parseFloat(ownershipPct)
    if (purchasePrice.trim() !== '' && pp == null) return
    if (currentValue.trim() !== '' && cv == null) return
    if (Number.isNaN(ownershipNum) || ownershipNum < 0 || ownershipNum > 100) return

    onCreate({
      name: name.trim() || 'Asset',
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

  const inputCls = 'mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm text-zinc-900'
  const inputNumCls = `${inputCls} text-right tabular-nums`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-zinc-900">Add asset</h2>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="col-span-2 text-xs font-medium text-zinc-600">
              Name *
              <input
                className={inputCls}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Apartment Koramangala"
                required
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Type
              <select className={inputCls} value={type} onChange={(e) => setType(e.target.value)}>
                {ASSET_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Status
              <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
                {ASSET_STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Purchase date
              <input type="date" className={inputCls} value={purchaseDate} onChange={(e) => setPurchaseDate(e.target.value)} />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Ownership %
              <input
                className={inputNumCls}
                inputMode="decimal"
                value={ownershipPct}
                onChange={(e) => setOwnershipPct(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Purchase price (₹)
              <input
                className={inputNumCls}
                inputMode="decimal"
                placeholder="optional"
                value={purchasePrice}
                onChange={(e) => setPurchasePrice(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Current value (₹)
              <input
                className={inputNumCls}
                inputMode="decimal"
                placeholder="optional"
                value={currentValue}
                onChange={(e) => setCurrentValue(e.target.value)}
              />
            </label>
            <label className="col-span-2 text-xs font-medium text-zinc-600">
              Co-owner
              <input
                className={inputCls}
                placeholder="optional"
                value={coOwner}
                onChange={(e) => setCoOwner(e.target.value)}
              />
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
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-2">
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
              {isPending ? 'Adding…' : 'Add asset'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
