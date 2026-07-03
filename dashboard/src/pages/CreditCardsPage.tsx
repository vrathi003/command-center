import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { fetchCreditCards, postCreditCard } from '@/lib/api'
import { formatPaiseCompact } from '@/lib/format'


function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n < 0) {
    return null
  }
  return Math.round(n * 100)
}

export function CreditCardsPage() {
  const qc = useQueryClient()
  const q = useQuery({
    queryKey: ['credit-cards'],
    queryFn: () => fetchCreditCards(false),
  })

  const [name, setName] = useState('')
  const [issuer, setIssuer] = useState('')
  const [lastFour, setLastFour] = useState('')
  const [limitRupees, setLimitRupees] = useState('100000')
  const [balRupees, setBalRupees] = useState('')

  const create = useMutation({
    mutationFn: postCreditCard,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['credit-cards'] }),
  })

  if (q.isPending) {
    return <PageLoading lines={3} />
  }

  if (q.isError) {
    return (
      <PageError title="Could not load credit cards" message={<p className="text-sm">{String(q.error)}</p>} />
    )
  }

  const rows = q.data ?? []

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Borrowing"
        title="Credit cards"
        description="Set limits and balances, upload statements on each card’s page, and import transactions after review."
        actions={
          <Link
            to="/credit-cards/statements"
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 shadow-sm transition hover:bg-zinc-50"
          >
            Statement inbox
          </Link>
        }
      />

      <section>
        <SectionTitle>Add a card</SectionTitle>
        <Panel variant="emerald">
          <form
            className="flex flex-col gap-3 lg:flex-row lg:flex-wrap lg:items-end"
            onSubmit={(e) => {
              e.preventDefault()
              const lim = rupeesToPaise(limitRupees)
              if (lim == null) {
                return
              }
              const bal = balRupees.trim() === '' ? null : rupeesToPaise(balRupees)
              if (balRupees.trim() !== '' && bal == null) {
                return
              }
              create.mutate({
                name: name.trim() || 'Card',
                issuer: issuer.trim() || null,
                last_four: lastFour.trim() || null,
                credit_limit_paise: lim,
                current_balance_paise: bal,
                notes: null,
                is_active: true,
              })
              setName('')
              setIssuer('')
              setLastFour('')
            }}
          >
            <label className="text-xs font-medium text-zinc-700">
              Name
              <input
                className="mt-1 block h-10 min-w-[10rem] rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="HDFC Regalia"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Issuer
              <input
                className="mt-1 block h-10 w-40 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={issuer}
                onChange={(e) => setIssuer(e.target.value)}
                placeholder="HDFC"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Last 4 digits
              <input
                className="mt-1 block h-10 w-24 rounded-lg border border-zinc-200 bg-white px-3 text-sm shadow-sm"
                value={lastFour}
                onChange={(e) => setLastFour(e.target.value.replace(/\D/g, '').slice(0, 4))}
                inputMode="numeric"
                placeholder="1234"
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Credit limit (₹)
              <input
                className="mt-1 block h-10 w-32 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={limitRupees}
                onChange={(e) => setLimitRupees(e.target.value)}
              />
            </label>
            <label className="text-xs font-medium text-zinc-700">
              Current balance (₹)
              <input
                className="mt-1 block h-10 w-32 rounded-lg border border-zinc-200 bg-white px-3 text-right text-sm tabular-nums shadow-sm"
                inputMode="decimal"
                value={balRupees}
                onChange={(e) => setBalRupees(e.target.value)}
                placeholder="optional"
              />
            </label>
            <button
              type="submit"
              disabled={create.isPending}
              className="h-10 rounded-lg bg-emerald-700 px-5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-50"
            >
              Add card
            </button>
          </form>
          {create.isError ? <p className="mt-3 text-sm text-red-600">{String(create.error)}</p> : null}
        </Panel>
      </section>

      <section>
        <SectionTitle>Your cards</SectionTitle>
        {rows.length === 0 ? (
          <Panel className="text-center text-sm text-zinc-600">No cards yet — add one above.</Panel>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((c) => (
              <Link
                key={c.id}
                to={`/credit-cards/${c.id}`}
                className="group block rounded-2xl border border-zinc-200/80 bg-white p-5 shadow-md shadow-zinc-900/5 ring-1 ring-zinc-900/[0.04] transition hover:-translate-y-0.5 hover:shadow-lg hover:ring-emerald-200/80"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-semibold text-zinc-900 group-hover:text-emerald-900">{c.name}</p>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {[c.issuer, c.last_four ? `···${c.last_four}` : null].filter(Boolean).join(' · ') ||
                        '—'}
                    </p>
                  </div>
                  {c.utilization_pct != null ? (
                    <span className="shrink-0 rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-semibold tabular-nums text-zinc-800">
                      {c.utilization_pct.toFixed(0)}% util
                    </span>
                  ) : (
                    <span className="text-xs text-zinc-400">—</span>
                  )}
                </div>
                <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <p className="text-zinc-500">Limit</p>
                    <p className="font-medium tabular-nums text-zinc-900">{formatPaiseCompact(c.credit_limit_paise)}</p>
                  </div>
                  <div>
                    <p className="text-zinc-500">Balance</p>
                    <p className="font-medium tabular-nums text-zinc-900">
                      {c.current_balance_paise != null ? formatPaiseCompact(c.current_balance_paise) : '—'}
                    </p>
                  </div>
                  {(c.emi_monthly_due_paise ?? 0) > 0 ? (
                    <div className="col-span-2 rounded-lg bg-zinc-50 px-2 py-1.5">
                      <p className="text-zinc-500">EMI / month (active plans)</p>
                      <p className="font-medium tabular-nums text-zinc-900">
                        {formatPaiseCompact(c.emi_monthly_due_paise ?? 0)}
                      </p>
                    </div>
                  ) : null}
                </div>
                <p className="mt-3 text-xs font-medium text-emerald-800">Open card →</p>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
