import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'

import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { SectionTitle } from '@/components/ui/SectionTitle'
import {
  deleteAccount,
  fetchAccounts,
  postAccount,
  putAccount,
} from '@/lib/api'
import type { AccountOut } from '@/types/api'

const ACCOUNT_TYPES = [
  { value: 'savings', label: 'Savings account' },
  { value: 'current', label: 'Current account' },
  { value: 'credit_card', label: 'Credit card' },
  { value: 'wallet', label: 'Wallet / UPI' },
  { value: 'investment', label: 'Investment account' },
  { value: 'loan', label: 'Loan account' },
  { value: 'other', label: 'Other' },
]

const TYPE_LABELS: Record<string, string> = Object.fromEntries(
  ACCOUNT_TYPES.map((t) => [t.value, t.label]),
)

const TYPE_ICONS: Record<string, string> = {
  savings: '🏦',
  current: '🏢',
  credit_card: '💳',
  wallet: '👛',
  investment: '📈',
  loan: '💸',
  other: '🗂️',
}

const BLANK_FORM = {
  name: '',
  type: 'savings',
  institution: '',
  currency: 'INR',
  is_active: true,
}

type FormState = typeof BLANK_FORM

function AccountForm({
  initial,
  onSave,
  onCancel,
  isPending,
  error,
}: {
  initial: FormState
  onSave: (f: FormState) => void
  onCancel: () => void
  isPending: boolean
  error: string | null
}) {
  const [form, setForm] = useState<FormState>(initial)
  const set = (k: keyof FormState, v: string | boolean) =>
    setForm((p) => ({ ...p, [k]: v }))

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-zinc-700">
          <span className="font-medium">Account name *</span>
          <input
            type="text"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="e.g. HDFC Savings, SBI Current"
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-zinc-700">
          <span className="font-medium">Type *</span>
          <select
            value={form.type}
            onChange={(e) => set('type', e.target.value)}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          >
            {ACCOUNT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-zinc-700">
          <span className="font-medium">Institution</span>
          <input
            type="text"
            value={form.institution}
            onChange={(e) => set('institution', e.target.value)}
            placeholder="e.g. HDFC Bank, SBI"
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-zinc-700">
          <span className="font-medium">Currency</span>
          <input
            type="text"
            value={form.currency}
            onChange={(e) => set('currency', e.target.value)}
            placeholder="INR"
            maxLength={5}
            className="rounded-lg border border-zinc-200 px-3 py-2 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
        </label>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-700">
        <input
          type="checkbox"
          checked={form.is_active}
          onChange={(e) => set('is_active', e.target.checked)}
          className="h-4 w-4 rounded border-zinc-300 text-emerald-700 focus:ring-emerald-600"
        />
        Active (appears in import selector and filters)
      </label>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          disabled={isPending || !form.name.trim()}
          onClick={() => onSave(form)}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:pointer-events-none disabled:opacity-40"
        >
          {isPending ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export function AccountsPage() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [formError, setFormError] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ['accounts'],
    queryFn: () => fetchAccounts(),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['accounts'] })
    void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
  }

  const createMut = useMutation({
    mutationFn: postAccount,
    onSuccess: () => {
      invalidate()
      setShowAdd(false)
      setFormError(null)
    },
    onError: (e) => setFormError(String(e)),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Parameters<typeof putAccount>[1] }) =>
      putAccount(id, body),
    onSuccess: () => {
      invalidate()
      setEditId(null)
      setFormError(null)
    },
    onError: (e) => setFormError(String(e)),
  })

  const deleteMut = useMutation({
    mutationFn: deleteAccount,
    onSuccess: invalidate,
    onError: (e) => alert(String(e)),
  })

  const accounts = useMemo(() => q.data ?? [], [q.data])
  const active = accounts.filter((a) => a.is_active)
  const inactive = accounts.filter((a) => !a.is_active)

  if (q.isPending) return <PageLoading lines={3} showFooterBlock />
  if (q.isError)
    return (
      <PageError
        title="Failed to load accounts"
        message={<p className="text-sm">{String(q.error)}</p>}
      />
    )

  const handleSave = (form: FormState, existing?: AccountOut) => {
    if (!form.name.trim()) return
    if (existing) {
      updateMut.mutate({
        id: existing.id,
        body: {
          name: form.name.trim(),
          type: form.type,
          institution: form.institution.trim() || null,
          currency: form.currency.trim() || 'INR',
          is_active: form.is_active,
        },
      })
    } else {
      createMut.mutate({
        name: form.name.trim(),
        type: form.type,
        institution: form.institution.trim() || null,
        currency: form.currency.trim() || 'INR',
      })
    }
  }

  const handleDelete = (a: AccountOut) => {
    if (!window.confirm(`Delete account "${a.name}"? Transactions linked to it will keep the account name but you won't be able to manage this account anymore.`)) return
    deleteMut.mutate(a.id)
  }

  const AccountCard = ({ a }: { a: AccountOut }) => {
    const isEditing = editId === a.id
    return (
      <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm">
        {isEditing ? (
          <AccountForm
            initial={{
              name: a.name,
              type: a.type,
              institution: a.institution ?? '',
              currency: a.currency,
              is_active: a.is_active,
            }}
            onSave={(f) => handleSave(f, a)}
            onCancel={() => { setEditId(null); setFormError(null) }}
            isPending={updateMut.isPending}
            error={formError}
          />
        ) : (
          <div className="flex items-start gap-3">
            <span className="mt-0.5 text-2xl leading-none">
              {TYPE_ICONS[a.type] ?? '🗂️'}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-zinc-900">{a.name}</p>
                {!a.is_active && (
                  <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-500">
                    Inactive
                  </span>
                )}
              </div>
              <p className="text-sm text-zinc-500">
                {TYPE_LABELS[a.type] ?? a.type}
                {a.institution ? ` · ${a.institution}` : ''}
                {a.currency !== 'INR' ? ` · ${a.currency}` : ''}
              </p>
            </div>
            <div className="flex shrink-0 gap-1">
              <button
                type="button"
                onClick={() => { setEditId(a.id); setFormError(null) }}
                className="rounded-lg border border-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-50"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={() => handleDelete(a)}
                disabled={deleteMut.isPending}
                className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
              >
                Delete
              </button>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-10">
      <PageHero
        eyebrow="Accounts"
        title="My Accounts"
        description={`${active.length} active account${active.length !== 1 ? 's' : ''} · bank, credit card, wallet`}
      />

      <section>
        <div className="mb-3 flex items-center justify-between">
          <SectionTitle>Accounts</SectionTitle>
          {!showAdd && (
            <button
              type="button"
              onClick={() => { setShowAdd(true); setFormError(null) }}
              className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800"
            >
              + Add account
            </button>
          )}
        </div>

        {showAdd && (
          <Panel className="mb-4">
            <p className="mb-3 text-sm font-medium text-zinc-700">New account</p>
            <AccountForm
              initial={BLANK_FORM}
              onSave={(f) => handleSave(f)}
              onCancel={() => { setShowAdd(false); setFormError(null) }}
              isPending={createMut.isPending}
              error={formError}
            />
          </Panel>
        )}

        {accounts.length === 0 ? (
          <Panel>
            <p className="text-sm text-zinc-500">
              No accounts yet. Add your bank accounts, credit cards, and wallets above — then select
              the account when importing a statement so transactions are tagged automatically.
            </p>
          </Panel>
        ) : (
          <div className="space-y-3">
            {active.map((a) => (
              <AccountCard key={a.id} a={a} />
            ))}
            {inactive.length > 0 && (
              <>
                <p className="pt-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
                  Inactive
                </p>
                {inactive.map((a) => (
                  <AccountCard key={a.id} a={a} />
                ))}
              </>
            )}
          </div>
        )}
      </section>

      <section>
        <SectionTitle>How accounts work</SectionTitle>
        <Panel>
          <ul className="space-y-2 text-sm text-zinc-600">
            <li>
              <strong className="font-medium text-zinc-800">Import tagging</strong> — when you
              upload a bank statement, select the account from the dropdown. Every transaction in
              that file is tagged to that account.
            </li>
            <li>
              <strong className="font-medium text-zinc-800">Filter by account</strong> — on the
              Transactions page, filter the ledger to any single account to see its statement
              in-app.
            </li>
            <li>
              <strong className="font-medium text-zinc-800">Dashboard breakdown</strong> — the
              Overview page shows this month's spending split by account so you know which account
              you're spending from most.
            </li>
            <li>
              <strong className="font-medium text-zinc-800">Account name in file</strong> — if
              your CSV/Excel has an <code className="text-xs">account</code> or{' '}
              <code className="text-xs">bank_account</code> column, that value is used directly
              and takes precedence over the import selector.
            </li>
          </ul>
        </Panel>
      </section>
    </div>
  )
}
