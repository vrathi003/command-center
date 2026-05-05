import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useEffect, useState } from 'react'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import {
  HOME_ITEM_CATEGORIES,
  HOME_ITEM_CONDITIONS,
  HOME_SERVICE_EVENT_TYPES,
} from '@/constants/home_inventory'
import {
  deleteHomeItem,
  deleteHomeItemServiceEvent,
  fetchHomeItem,
  fetchHomeItemServiceEvents,
  postHomeItemServiceEvent,
  putHomeItem,
  putHomeItemServiceEvent,
} from '@/lib/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'
import type { HomeItemOut, HomeItemServiceEventOut } from '@/types/api'

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) return null
  return Math.round(n * 100)
}

function categoryLabel(c: string): string {
  return c.replace(/_/g, ' ')
}

function parseId(raw: string | undefined): number | null {
  if (!raw) return null
  const n = Number.parseInt(raw, 10)
  return Number.isNaN(n) ? null : n
}

export function HomeItemDetailPage() {
  const { itemId: itemIdParam } = useParams()
  const itemId = parseId(itemIdParam)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const item = useQuery({
    queryKey: ['home-item', itemId],
    queryFn: () => fetchHomeItem(itemId!),
    enabled: itemId != null,
  })

  const events = useQuery({
    queryKey: ['home-item-events', itemId],
    queryFn: () => fetchHomeItemServiceEvents(itemId!),
    enabled: itemId != null,
  })

  const [name, setName] = useState('')
  const [category, setCategory] = useState('other')
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [serial, setSerial] = useState('')
  const [room, setRoom] = useState('')
  const [purchaseDate, setPurchaseDate] = useState('')
  const [purchaseRupees, setPurchaseRupees] = useState('')
  const [retailer, setRetailer] = useState('')
  const [warrantyEnd, setWarrantyEnd] = useState('')
  const [extended, setExtended] = useState(false)
  const [condition, setCondition] = useState('good')
  const [notes, setNotes] = useState('')

  useEffect(() => {
    const d = item.data
    if (!d) return
    /* eslint-disable react-hooks/set-state-in-effect -- hydrate item form from query */
    setName(d.name)
    setCategory(d.category)
    setBrand(d.brand ?? '')
    setModel(d.model ?? '')
    setSerial(d.serial_number ?? '')
    setRoom(d.room_location ?? '')
    setPurchaseDate(d.purchase_date ?? '')
    setPurchaseRupees(d.purchase_price_paise != null ? String(d.purchase_price_paise / 100) : '')
    setRetailer(d.retailer ?? '')
    setWarrantyEnd(d.warranty_end_date ?? '')
    setExtended(d.extended_warranty)
    setCondition(d.condition_status)
    setNotes(d.notes ?? '')
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [item.data])

  const [svcDate, setSvcDate] = useState('')
  const [svcType, setSvcType] = useState<string>(HOME_SERVICE_EVENT_TYPES[0])
  const [svcVendor, setSvcVendor] = useState('')
  const [svcDesc, setSvcDesc] = useState('')
  const [svcCost, setSvcCost] = useState('')
  const [svcNext, setSvcNext] = useState('')
  const [svcNotes, setSvcNotes] = useState('')
  const [editingEvent, setEditingEvent] = useState<HomeItemServiceEventOut | null>(null)

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- service event editor draft */
    if (editingEvent) {
      setSvcDate(editingEvent.service_date)
      setSvcType(editingEvent.event_type)
      setSvcVendor(editingEvent.vendor ?? '')
      setSvcDesc(editingEvent.description ?? '')
      setSvcCost(editingEvent.cost_paise != null ? String(editingEvent.cost_paise / 100) : '')
      setSvcNext(editingEvent.next_service_due ?? '')
      setSvcNotes(editingEvent.notes ?? '')
    } else {
      setSvcDate('')
      setSvcType(HOME_SERVICE_EVENT_TYPES[0])
      setSvcVendor('')
      setSvcDesc('')
      setSvcCost('')
      setSvcNext('')
      setSvcNotes('')
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [editingEvent])

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['home-item', itemId] })
    void qc.invalidateQueries({ queryKey: ['home-item-events', itemId] })
    void qc.invalidateQueries({ queryKey: ['home-items'] })
    void qc.invalidateQueries({ queryKey: ['home-inventory-summary'] })
  }

  const saveItem = useMutation({
    mutationFn: () => {
      const p = purchaseRupees.trim() === '' ? null : rupeesToPaise(purchaseRupees)
      if (purchaseRupees.trim() !== '' && p == null) {
        return Promise.reject(new Error('Invalid purchase price'))
      }
      return putHomeItem(itemId!, {
        name: name.trim() || 'Item',
        category,
        brand: brand.trim() || null,
        model: model.trim() || null,
        serial_number: serial.trim() || null,
        room_location: room.trim() || null,
        purchase_date: purchaseDate.trim() || null,
        purchase_price_paise: p,
        retailer: retailer.trim() || null,
        warranty_end_date: warrantyEnd.trim() || null,
        extended_warranty: extended,
        condition_status: condition,
        notes: notes.trim() || null,
      })
    },
    onSuccess: invalidate,
  })

  const removeItem = useMutation({
    mutationFn: () => deleteHomeItem(itemId!),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['home-items'] })
      void qc.invalidateQueries({ queryKey: ['home-inventory-summary'] })
      navigate('/home')
    },
  })

  const saveEvent = useMutation({
    mutationFn: () => {
      const costPaise = svcCost.trim() === '' ? null : rupeesToPaise(svcCost)
      if (svcCost.trim() !== '' && costPaise == null) {
        return Promise.reject(new Error('Invalid cost'))
      }
      const body = {
        service_date: svcDate,
        event_type: svcType,
        vendor: svcVendor.trim() || null,
        description: svcDesc.trim() || null,
        cost_paise: costPaise,
        next_service_due: svcNext.trim() || null,
        notes: svcNotes.trim() || null,
      }
      if (editingEvent) {
        return putHomeItemServiceEvent(itemId!, editingEvent.id, body)
      }
      return postHomeItemServiceEvent(itemId!, body)
    },
    onSuccess: () => {
      invalidate()
      setEditingEvent(null)
    },
  })

  const delEvent = useMutation({
    mutationFn: (eid: number) => deleteHomeItemServiceEvent(itemId!, eid),
    onSuccess: invalidate,
  })

  if (itemId == null) {
    return <PageError title="Invalid item" message={<p className="text-sm">Bad link.</p>} />
  }

  if (item.isPending || events.isPending) return <PageLoading lines={4} />
  if (item.isError || events.isError) {
    return (
      <PageError
        title="Could not load item"
        message={<p className="text-sm">{String(item.error ?? events.error)}</p>}
      />
    )
  }

  const d: HomeItemOut = item.data

  const totalService =
    events.data?.reduce((s, e) => s + (e.cost_paise ?? 0), 0) ?? 0

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <Link
            to="/home"
            className="mb-2 inline-block text-sm font-medium text-emerald-800 hover:underline"
          >
            ← Home Inventory
          </Link>
          <PageHero
            eyebrow="Household"
            title={d.name}
            description={`${categoryLabel(d.category)}${d.room_location ? ` · ${d.room_location}` : ''}`}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={saveItem.isPending}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            onClick={() => saveItem.mutate()}
          >
            {saveItem.isPending ? 'Saving…' : 'Save changes'}
          </button>
          <button
            type="button"
            disabled={removeItem.isPending}
            className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
            onClick={() => {
              if (window.confirm('Delete this item and all service history?')) {
                removeItem.mutate()
              }
            }}
          >
            Delete item
          </button>
        </div>
      </div>

      <section className="grid gap-4 sm:grid-cols-3">
        <Panel className="p-4">
          <p className="text-[10px] font-semibold uppercase text-zinc-500">Purchase</p>
          <p className="mt-1 text-lg font-bold tabular-nums text-zinc-900">
            {d.purchase_price_paise != null ? formatPaiseCompact(d.purchase_price_paise) : '—'}
          </p>
          <p className="text-xs text-zinc-500">{d.purchase_date ?? 'No date'}</p>
        </Panel>
        <Panel className="p-4">
          <p className="text-[10px] font-semibold uppercase text-zinc-500">Service spend (logged)</p>
          <p className="mt-1 text-lg font-bold tabular-nums text-zinc-900">
            {formatPaiseCompact(totalService)}
          </p>
          <p className="text-xs text-zinc-500">{events.data?.length ?? 0} event(s)</p>
        </Panel>
        <Panel className="p-4">
          <p className="text-[10px] font-semibold uppercase text-zinc-500">Warranty</p>
          <p className="mt-1 text-sm font-semibold text-zinc-900">
            {d.warranty_end_date ?? '—'}
          </p>
          <p className="text-xs text-zinc-500">
            {d.extended_warranty ? 'Extended warranty noted' : 'Standard'}
          </p>
        </Panel>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-zinc-800">Item details</h2>
        <Panel>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="text-xs font-medium text-zinc-600">
              Name
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
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
            <label className="text-xs font-medium text-zinc-600">
              Brand
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={brand}
                onChange={(e) => setBrand(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Model
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Serial number
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={serial}
                onChange={(e) => setSerial(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Room / location
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={room}
                onChange={(e) => setRoom(e.target.value)}
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
              Retailer
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={retailer}
                onChange={(e) => setRetailer(e.target.value)}
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
            <label className="flex items-center gap-2 pt-6 text-xs font-medium text-zinc-600">
              <input
                type="checkbox"
                checked={extended}
                onChange={(e) => setExtended(e.target.checked)}
                className="rounded border-zinc-300"
              />
              Extended warranty
            </label>
            <label className="sm:col-span-2 lg:col-span-3 text-xs font-medium text-zinc-600">
              Notes
              <textarea
                className="mt-1 block min-h-[72px] w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
          </div>
          {saveItem.isError ? (
            <p className="mt-2 text-sm text-red-600">{String(saveItem.error)}</p>
          ) : null}
        </Panel>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-zinc-800">Maintenance & service</h2>
        <Panel variant="table" padding={false} className="overflow-x-auto">
          <table className="w-full min-w-[800px] border-collapse text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-600">
              <tr>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Vendor</th>
                <th className="px-3 py-2">Description</th>
                <th className="px-3 py-2 text-right">Cost</th>
                <th className="px-3 py-2">Next due</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200">
              {(events.data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-zinc-500">
                    No service events yet — add one below.
                  </td>
                </tr>
              ) : (
                (events.data ?? []).map((ev) => (
                  <tr key={ev.id} className="hover:bg-zinc-50/80">
                    <td className="px-3 py-2 tabular-nums text-zinc-800">{ev.service_date}</td>
                    <td className="px-3 py-2 text-zinc-700">{categoryLabel(ev.event_type)}</td>
                    <td className="px-3 py-2 text-zinc-600">{ev.vendor ?? '—'}</td>
                    <td className="max-w-[220px] px-3 py-2 text-zinc-600">
                      {ev.description ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-zinc-800">
                      {ev.cost_paise != null ? formatPaise(ev.cost_paise) : '—'}
                    </td>
                    <td className="px-3 py-2 text-zinc-600">{ev.next_service_due ?? '—'}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        className="mr-2 text-xs font-medium text-emerald-800 hover:underline"
                        onClick={() => setEditingEvent(ev)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        disabled={delEvent.isPending}
                        className="text-xs font-medium text-red-700 hover:underline disabled:opacity-50"
                        onClick={() => {
                          if (window.confirm('Delete this service event?')) {
                            delEvent.mutate(ev.id)
                          }
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Panel>

        <Panel className="mt-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
            {editingEvent ? 'Edit service event' : 'Add service event'}
          </p>
          <form
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
            onSubmit={(e) => {
              e.preventDefault()
              if (!svcDate.trim()) return
              saveEvent.mutate()
            }}
          >
            <label className="text-xs font-medium text-zinc-600">
              Service date *
              <input
                type="date"
                required
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={svcDate}
                onChange={(e) => setSvcDate(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Type
              <select
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={svcType}
                onChange={(e) => setSvcType(e.target.value)}
              >
                {HOME_SERVICE_EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {categoryLabel(t)}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Vendor
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={svcVendor}
                onChange={(e) => setSvcVendor(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Cost (₹)
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-right text-sm tabular-nums"
                inputMode="decimal"
                value={svcCost}
                onChange={(e) => setSvcCost(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-600">
              Next service due
              <input
                type="date"
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={svcNext}
                onChange={(e) => setSvcNext(e.target.value)}
              />
            </label>
            <label className="sm:col-span-2 text-xs font-medium text-zinc-600">
              Description
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={svcDesc}
                onChange={(e) => setSvcDesc(e.target.value)}
              />
            </label>
            <label className="sm:col-span-2 lg:col-span-3 text-xs font-medium text-zinc-600">
              Notes
              <input
                className="mt-1 block w-full rounded border border-zinc-200 px-2 py-1.5 text-sm"
                value={svcNotes}
                onChange={(e) => setSvcNotes(e.target.value)}
              />
            </label>
            <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-3">
              <button
                type="submit"
                disabled={saveEvent.isPending}
                className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
              >
                {saveEvent.isPending ? 'Saving…' : editingEvent ? 'Update event' : 'Add event'}
              </button>
              {editingEvent ? (
                <button
                  type="button"
                  className="rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
                  onClick={() => setEditingEvent(null)}
                >
                  Cancel edit
                </button>
              ) : null}
            </div>
          </form>
          {saveEvent.isError ? (
            <p className="mt-2 text-sm text-red-600">{String(saveEvent.error)}</p>
          ) : null}
        </Panel>
      </section>
    </div>
  )
}
