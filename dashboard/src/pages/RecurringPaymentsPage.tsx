import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { KpiCard } from '@/components/dashboard/KpiCard'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { deleteSubscription, fetchDebts, fetchSubscriptions, postSubscription, putSubscription } from '@/lib/api'
import { formatPaise, formatPaiseCompact } from '@/lib/format'
import type { SubscriptionOut } from '@/types/api'


const BILLING_CYCLES = ['weekly', 'monthly', 'quarterly', 'yearly'] as const

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) {
    return null
  }
  return Math.round(n * 100)
}

export function RecurringPaymentsPage() {
  const qc = useQueryClient()
  const subs = useQuery({
    queryKey: ['subscriptions'],
    queryFn: () => fetchSubscriptions(false),
  })
  const debts = useQuery({
    queryKey: ['debts'],
    queryFn: fetchDebts,
  })

  const [nName, setNName] = useState('')
  const [nProvider, setNProvider] = useState('')
  const [nCategory, setNCategory] = useState('')
  const [nAmt, setNAmt] = useState('499')
  const [nCycle, setNCycle] = useState<string>('monthly')
  const [nNext, setNNext] = useState('')
  const [nNotes, setNNotes] = useState('')

  const create = useMutation({
    mutationFn: postSubscription,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['subscriptions'] }),
  })

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof putSubscription>[1] }) =>
      putSubscription(id, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['subscriptions'] }),
  })

  const remove = useMutation({
    mutationFn: deleteSubscription,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['subscriptions'] }),
  })

  const emiRows = useMemo(() => {
    const rows = (debts.data ?? []).filter(
      (d) => d.status === 'active' && d.emi_paise != null && d.emi_paise > 0,
    )
    return [...rows].sort((a, b) => {
      const da = a.next_emi_date ?? ''
      const db = b.next_emi_date ?? ''
      if (!da && !db) {
        return a.name.localeCompare(b.name)
      }
      if (!da) {
        return 1
      }
      if (!db) {
        return -1
      }
      return da.localeCompare(db)
    })
  }, [debts.data])

  const subTotals = useMemo(() => {
    const active = (subs.data ?? []).filter((s) => s.is_active)
    const monthlyEq = active.reduce((acc, s) => acc + s.monthly_equivalent_paise, 0)
    return { count: active.length, monthlyEq }
  }, [subs.data])

  const emiMonthlyTotal = useMemo(
    () => emiRows.reduce((acc, d) => acc + (d.emi_paise ?? 0), 0),
    [emiRows],
  )

  if (subs.isPending || debts.isPending) {
    return <PageLoading lines={4} showFooterBlock />
  }

  if (subs.isError || debts.isError) {
    return (
      <PageError
        title="Could not load recurring data"
        message={(
          <p className="text-sm">{String(subs.error ?? debts.error)}</p>
        )}
      />
    )
  }

  const combinedMonthly = subTotals.monthlyEq + emiMonthlyTotal

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Cash outflows"
        title="Subscriptions & EMIs"
        description={
          <>
            Track recurring subscriptions (monthly equivalent) and loan EMIs from{' '}
            <Link to="/debt" className="font-medium text-emerald-800 underline">
              Debt
            </Link>
            . Refreshes every 30s.
          </>
        }
      />

      <section className="grid gap-4 sm:grid-cols-3">
        <KpiCard
          tone="spending"
          label="Subscriptions (monthly eq.)"
          value={formatPaiseCompact(subTotals.monthlyEq)}
          hint={subTotals.count ? `${subTotals.count} active` : 'None active'}
        />
        <KpiCard
          tone="balance"
          label="Loan EMIs (monthly)"
          value={formatPaiseCompact(emiMonthlyTotal)}
          hint={emiRows.length ? `${emiRows.length} with EMI` : 'No EMIs on file'}
        />
        <KpiCard
          tone="neutral"
          label="Combined monthly"
          value={formatPaiseCompact(combinedMonthly)}
        />
      </section>

      <section>
        <SectionTitle>Subscriptions</SectionTitle>
        <Panel variant="emerald">
          <h2 className="sr-only">Add subscription</h2>
          <p className="mb-4 text-xs text-zinc-600">
            Amount is per billing period (e.g. ₹499/month or ₹4,999/year). We show a monthly equivalent
            for totals.
          </p>
          <form
            className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end"
            onSubmit={(e) => {
              e.preventDefault()
              const paise = rupeesToPaise(nAmt)
              if (paise == null) {
                return
              }
              create.mutate({
                name: nName.trim() || 'Subscription',
                provider: nProvider.trim() || null,
                category: nCategory.trim() || null,
                amount_paise: paise,
                billing_cycle: nCycle,
                next_billing_date: nNext.trim() || null,
                notes: nNotes.trim() || null,
                is_active: true,
              })
              setNName('')
              setNProvider('')
              setNCategory('')
              setNNotes('')
            }}
          >
            <label className="text-xs font-medium text-zinc-700">
              Name
              <input
                className="mt-1 block h-10 min-w-[10rem] rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={nName}
                onChange={(e) => setNName(e.target.value)}
                placeholder="Netflix"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Provider
              <input
                className="mt-1 block h-10 min-w-[8rem] rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={nProvider}
                onChange={(e) => setNProvider(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Category
              <input
                className="mt-1 block h-10 w-36 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={nCategory}
                onChange={(e) => setNCategory(e.target.value)}
                placeholder="Streaming"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Amount (₹ / period)
              <input
                className="mt-1 block h-10 w-28 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={nAmt}
                onChange={(e) => setNAmt(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Cycle
              <select
                className="mt-1 block h-10 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={nCycle}
                onChange={(e) => setNCycle(e.target.value)}
              >
                {BILLING_CYCLES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Next billing
              <input
                type="date"
                className="mt-1 block h-10 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={nNext}
                onChange={(e) => setNNext(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Notes
              <input
                className="mt-1 block h-10 min-w-[10rem] rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={nNotes}
                onChange={(e) => setNNotes(e.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={create.isPending}
              className="h-10 rounded-lg bg-emerald-700 px-5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-50"
            >
              Add
            </button>
          </form>
          {create.isError ? <p className="mt-3 text-sm text-red-600">{String(create.error)}</p> : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Your subscriptions</SectionTitle>
        <Panel variant="table" padding={false} className="overflow-x-auto">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Provider</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3 text-right">Per period</th>
                <th className="px-4 py-3">Cycle</th>
                <th className="px-4 py-3 text-right">Monthly eq.</th>
                <th className="px-4 py-3">Next</th>
                <th className="px-4 py-3">Active</th>
                <th className="px-4 py-3"> </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {(subs.data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-zinc-500">
                    No subscriptions yet — add one above.
                  </td>
                </tr>
              ) : (
                (subs.data ?? []).map((s) => (
                  <SubscriptionRow
                    key={`${s.id}-${s.amount_paise}-${s.monthly_equivalent_paise}-${s.name}-${s.is_active ? 1 : 0}`}
                    row={s}
                    busy={update.isPending || remove.isPending}
                    onSave={(body) => update.mutate({ id: s.id, body })}
                    onDelete={() => remove.mutate(s.id)}
                  />
                ))
              )}
            </tbody>
          </table>
        </Panel>
        {update.isError ? <p className="mt-2 text-sm text-red-600">{String(update.error)}</p> : null}
      </section>

      <section>
        <SectionTitle>Loan EMIs</SectionTitle>
        <p className="mb-4 text-sm text-zinc-600">
          Pulled from active debts with an EMI set. Edit loans on the{' '}
          <Link to="/debt" className="font-medium text-emerald-800 underline">
            Debt
          </Link>{' '}
          page.
        </p>
        <Panel variant="table" padding={false} className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3">Loan</th>
                <th className="px-4 py-3">Lender</th>
                <th className="px-4 py-3 text-right">EMI</th>
                <th className="px-4 py-3">Next EMI</th>
                <th className="px-4 py-3 text-right">Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {emiRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-zinc-500">
                    No EMIs — add a loan with EMI on the Debt page.
                  </td>
                </tr>
              ) : (
                emiRows.map((d) => (
                  <tr key={d.id} className="hover:bg-zinc-50/80">
                    <td className="px-4 py-2.5 font-medium text-zinc-900">{d.name}</td>
                    <td className="px-4 py-2.5 text-zinc-600">{d.lender ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-zinc-900">
                      {formatPaise(d.emi_paise!)}
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-zinc-700">{d.next_emi_date ?? '—'}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-zinc-700">
                      {formatPaiseCompact(d.current_balance_paise)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </Panel>
      </section>
    </div>
  )
}

function SubscriptionRow({
  row,
  onSave,
  onDelete,
  busy,
}: {
  row: SubscriptionOut
  onSave: (body: Parameters<typeof putSubscription>[1]) => void
  busy: boolean
  onDelete: () => void
}) {
  const [name, setName] = useState(row.name)
  const [provider, setProvider] = useState(row.provider ?? '')
  const [category, setCategory] = useState(row.category ?? '')
  const [amt, setAmt] = useState(String(row.amount_paise / 100))
  const [cycle, setCycle] = useState(row.billing_cycle)
  const [next, setNext] = useState(row.next_billing_date ?? '')
  const [notes, setNotes] = useState(row.notes ?? '')
  const [active, setActive] = useState(row.is_active)

  const save = () => {
    const paise = rupeesToPaise(amt)
    if (paise == null) {
      return
    }
    onSave({
      name: name.trim() || row.name,
      provider: provider.trim() || null,
      category: category.trim() || null,
      amount_paise: paise,
      billing_cycle: cycle,
      next_billing_date: next.trim() || null,
      notes: notes.trim() || null,
      is_active: active,
    })
  }

  return (
    <tr className="align-top hover:bg-zinc-50/80">
      <td className="px-4 py-2">
        <input
          className="w-full min-w-[8rem] rounded border border-zinc-200 px-2 py-1 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <input
          className="w-full min-w-[6rem] rounded border border-zinc-200 px-2 py-1 text-sm"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <input
          className="w-full min-w-[5rem] rounded border border-zinc-200 px-2 py-1 text-sm"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        />
      </td>
      <td className="px-4 py-2 text-right">
        <input
          className="w-24 rounded border border-zinc-200 px-2 py-1 text-right text-sm tabular-nums"
          inputMode="decimal"
          value={amt}
          onChange={(e) => setAmt(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <select
          className="rounded border border-zinc-200 px-2 py-1 text-xs"
          value={cycle}
          onChange={(e) => setCycle(e.target.value)}
        >
          {BILLING_CYCLES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </td>
      <td className="px-4 py-2 text-right tabular-nums text-zinc-600">
        {formatPaiseCompact(row.monthly_equivalent_paise)}
      </td>
      <td className="px-4 py-2">
        <input
          type="date"
          className="rounded border border-zinc-200 px-2 py-1 text-xs"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
      </td>
      <td className="px-4 py-2">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-zinc-300 text-emerald-700"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
        />
      </td>
      <td className="px-4 py-2">
        <div className="flex flex-col gap-1 sm:flex-row">
          <button
            type="button"
            disabled={busy}
            className="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={save}
          >
            Save
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-50 disabled:opacity-50"
            onClick={() => {
              if (window.confirm(`Remove “${row.name}”?`)) {
                onDelete()
              }
            }}
          >
            Delete
          </button>
        </div>
        <input
          className="mt-2 w-full min-w-[8rem] rounded border border-zinc-200 px-2 py-1 text-xs"
          placeholder="Notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </td>
    </tr>
  )
}
