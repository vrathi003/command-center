import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  HOME_ITEM_CATEGORIES,
  HOME_ITEM_CONDITIONS,
} from '@/constants/home_inventory'
import {
  deleteHomeItem,
  fetchHomeInventorySummary,
  fetchHomeItems,
  postHomeItem,
} from '@/lib/api'
import { formatPaiseCompact } from '@/lib/format'

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) return null
  return Math.round(n * 100)
}

function categoryLabel(c: string): string {
  return c.replace(/_/g, ' ')
}

export function HomeInventoryPage() {
  const qc = useQueryClient()
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [name, setName] = useState('')
  const [category, setCategory] = useState<string>(HOME_ITEM_CATEGORIES[0])
  const [brand, setBrand] = useState('')
  const [room, setRoom] = useState('')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [purchaseRupees, setPurchaseRupees] = useState('')
  const [warrantyEnd, setWarrantyEnd] = useState('')
  const [condition, setCondition] = useState<string>(HOME_ITEM_CONDITIONS[0])

  const summary = useQuery({
    queryKey: ['home-inventory-summary'],
    queryFn: fetchHomeInventorySummary,
  })

  const items = useQuery({
    queryKey: ['home-items', categoryFilter],
    queryFn: () =>
      fetchHomeItems(
        categoryFilter ? { category: categoryFilter } : undefined,
      ),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['home-inventory-summary'] })
    void qc.invalidateQueries({ queryKey: ['home-items'] })
  }

  const create = useMutation({
    mutationFn: postHomeItem,
    onSuccess: () => {
      invalidate()
      setName('')
      setBrand('')
      setRoom('')
      setPurchaseDate('')
      setPurchaseRupees('')
      setWarrantyEnd('')
    },
  })

  const remove = useMutation({
    mutationFn: deleteHomeItem,
    onSuccess: invalidate,
  })

  const categoryOptions = useMemo(() => {
    const fromData = items.data ?? []
    const set = new Set<string>()
    fromData.forEach((i) => set.add(i.category))
    HOME_ITEM_CATEGORIES.forEach((c) => set.add(c))
    return [...set].sort()
  }, [items.data])

  if (summary.isPending || items.isPending) return <PageLoading lines={4} />
  if (summary.isError || items.isError) {
    return (
      <PageError
        title="Could not load Home Inventory"
        message={
          <p className="text-sm">{String(summary.error ?? items.error)}</p>
        }
      />
    )
  }

  const s = summary.data

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Household"
        title="Home Inventory"
        description="Appliances, furniture, and gear — purchase info, warranty, and service history per item."
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard tone="neutral" label="Items tracked" value={String(s.item_count)} />
        <KpiCard
          tone="balance"
          label="Purchase value (listed)"
          value={formatPaiseCompact(s.purchase_value_total_paise)}
        />
        <KpiCard
          tone="balance"
          label="Total service spend"
          value={formatPaiseCompact(s.service_spend_total_paise)}
        />
        <KpiCard
          tone="neutral"
          label="Warranties expiring (90d)"
          value={String(s.warranty_expiring_within_90_days)}
        />
      </section>

      {Object.keys(s.count_by_category).length > 0 ? (
        <Panel>
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            By category
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {Object.entries(s.count_by_category).map(([cat, n]) => (
              <span
                key={cat}
                className="rounded-full bg-zinc-100 px-3 py-1 text-xs text-zinc-700"
              >
                {categoryLabel(cat)}: {n}
              </span>
            ))}
          </div>
        </Panel>
      ) : null}

      <section>
        <SectionTitle>Add item</SectionTitle>
        <Panel>
          <form
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault()
              const p = purchaseRupees.trim() === '' ? null : rupeesToPaise(purchaseRupees)
              if (purchaseRupees.trim() !== '' && p == null) return
              create.mutate({
                name: name.trim() || 'Item',
                category,
                brand: brand.trim() || null,
                room_location: room.trim() || null,
                purchase_date: purchaseDate.trim() || null,
                purchase_price_paise: p,
                warranty_end_date: warrantyEnd.trim() || null,
                condition_status: condition,
              })
            }}
          >
            <label className="text-xs font-medium text-zinc-600">
              Name *
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Category
              <select
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                {HOME_ITEM_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel(c)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Brand
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Room / location
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={room}
                onChange={(e) => setRoom(e.target.value)}
                placeholder="e.g. Kitchen"
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Purchase date
              <input
                type="date"
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={purchaseDate}
                onChange={(e) => setPurchaseDate(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Purchase price (₹)
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={purchaseRupees}
                onChange={(e) => setPurchaseRupees(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Warranty end
              <input
                type="date"
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={warrantyEnd}
                onChange={(e) => setWarrantyEnd(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Condition
              <select
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
              >
                {HOME_ITEM_CONDITIONS.map((c) => (
                  <option key={c} value={c}>
                    {categoryLabel(c)}
                  </option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={create.isPending}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
              >
                Add item
              </button>
            </div>
          </form>
          {create.isError ? (
            <p className="mt-2 text-sm text-red-600">{String(create.error)}</p>
          ) : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Your items</SectionTitle>
        <Panel variant="table" padding={false} className="overflow-x-auto">
          <div className="flex flex-wrap items-center gap-2 border-b border-zinc-200 bg-zinc-50 px-3 py-2">
            <span className="text-xs text-zinc-500">Filter:</span>
            <select
              className="rounded border border-zinc-200 bg-white px-2 py-1 text-xs"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
            >
              <option value="">All categories</option>
              {categoryOptions.map((c) => (
                <option key={c} value={c}>
                  {categoryLabel(c)}
                </option>
              ))}
            </select>
          </div>
          <table className="w-full min-w-[900px] border-collapse text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-600">
              <tr>
                <th className="px-3 py-3">Name</th>
                <th className="px-3 py-3">Category</th>
                <th className="px-3 py-3">Room</th>
                <th className="px-3 py-3 text-right">Purchase</th>
                <th className="px-3 py-3">Warranty end</th>
                <th className="px-3 py-3 text-right">Service spend</th>
                <th className="px-3 py-3 text-center">Events</th>
                <th className="px-3 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200">
              {items.data.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-zinc-500">
                    No items yet — add one above.
                  </td>
                </tr>
              ) : (
                items.data.map((row) => (
                  <tr key={row.id} className="hover:bg-zinc-50/80">
                    <td className="px-3 py-2.5">
                      <Link
                        to={`/home/${row.id}`}
                        className="font-medium text-emerald-800 hover:underline"
                      >
                        {row.name}
                      </Link>
                      {row.brand || row.model ? (
                        <span className="mt-0.5 block text-xs text-zinc-500">
                          {[row.brand, row.model].filter(Boolean).join(' · ')}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-700">{categoryLabel(row.category)}</td>
                    <td className="px-3 py-2.5 text-zinc-600">{row.room_location ?? '—'}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-zinc-800">
                      {row.purchase_price_paise != null
                        ? formatPaiseCompact(row.purchase_price_paise)
                        : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-zinc-600">{row.warranty_end_date ?? '—'}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-zinc-800">
                      {formatPaiseCompact(row.total_service_spend_paise)}
                    </td>
                    <td className="px-3 py-2.5 text-center tabular-nums text-zinc-600">
                      {row.service_event_count}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        type="button"
                        disabled={remove.isPending}
                        className="text-xs font-medium text-red-700 hover:underline disabled:opacity-50"
                        onClick={() => {
                          if (window.confirm(`Remove “${row.name}” from Home Inventory?`)) {
                            remove.mutate(row.id)
                          }
                        }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Panel>
        {remove.isError ? (
          <p className="mt-2 text-sm text-red-600">{String(remove.error)}</p>
        ) : null}
      </section>
    </div>
  )
}
