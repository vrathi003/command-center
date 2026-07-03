import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { MANUAL_TX_CATEGORIES, PAYMENT_MODE_OPTIONS } from '@/constants/transactionForm'
import {
  fetchTransactionTemplates,
  postManualTransaction,
  postMerchantRule,
  postTransfer,
  putTransaction,
} from '@/lib/api'
import type { AccountOut, TransactionRow, TransactionTemplateOut } from '@/types/api'

/** Row to edit plus the other transfer leg when present in the loaded ledger (from parent cache). */
export type TransactionEditDraft = {
  row: TransactionRow
  peer: TransactionRow | null
}

function rupeesToPaise(s: string): number | null {
  const n = Number.parseFloat(s.replace(/,/g, ''))
  if (Number.isNaN(n) || n <= 0) return null
  return Math.round(n * 100)
}

type Props = {
  open: boolean
  onClose: () => void
  accounts: AccountOut[]
  /** Edit payload from the ledger (add mode when null). Avoids a detail GET that can 404. */
  editDraft: TransactionEditDraft | null
}

export function AddTransactionDrawer({ open, onClose, accounts, editDraft }: Props) {
  const qc = useQueryClient()
  const isEdit = editDraft != null
  const transactionIdToEdit = editDraft?.row.id ?? null
  const templatesQ = useQuery({
    queryKey: ['transaction-templates'],
    queryFn: fetchTransactionTemplates,
    enabled: open && !isEdit,
  })
  const [templateChoice, setTemplateChoice] = useState<string>('')
  const [kind, setKind] = useState<'debit' | 'credit' | 'transfer'>('debit')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [amountRupees, setAmountRupees] = useState('')
  const [category, setCategory] = useState<string>('Other')
  const [merchant, setMerchant] = useState('')
  const [paymentMode, setPaymentMode] = useState<string>('UPI')
  const [accountId, setAccountId] = useState<string>('')
  const [fromAccountId, setFromAccountId] = useState<string>('')
  const [toAccountId, setToAccountId] = useState<string>('')
  const [notes, setNotes] = useState('')
  const [tags, setTags] = useState('')
  const [createRule, setCreateRule] = useState(false)
  const [ruleMatchType, setRuleMatchType] = useState<'exact' | 'contains'>('exact')

  useEffect(() => {
    if (!open) {
      return
    }
    if (!isEdit) {
      /* eslint-disable react-hooks/set-state-in-effect -- reset create form when drawer opens */
      setDate(new Date().toISOString().slice(0, 10))
      setTemplateChoice('')
      setKind('debit')
      setAmountRupees('')
      setCategory('Other')
      setMerchant('')
      setPaymentMode('UPI')
      setAccountId('')
      setFromAccountId('')
      setToAccountId('')
      setNotes('')
      setTags('')
      setCreateRule(false)
      setRuleMatchType('exact')
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [open, isEdit])

  useEffect(() => {
    if (!open || !isEdit || !editDraft) {
      return
    }
    /* eslint-disable react-hooks/set-state-in-effect -- hydrate form from edit row */
    const d = editDraft.row
    const sib = editDraft.peer
    setDate(d.date)
    setAmountRupees((d.amount_paise / 100).toFixed(2))
    setNotes(d.notes ?? '')
    setTags(d.tags ?? '')
    setCreateRule(false)
    setRuleMatchType('exact')
    if (d.transaction_type === 'transfer') {
      setKind('transfer')
      if (!d.transfer_pair_id) {
        setCategory(d.category)
        setMerchant(d.merchant ?? '')
        setPaymentMode(d.payment_mode)
        if (d.account_id != null) {
          setAccountId(String(d.account_id))
        } else if (d.account) {
          const match = accounts.find((a) => a.name === d.account)
          setAccountId(match ? String(match.id) : '')
        } else {
          setAccountId('')
        }
        setFromAccountId('')
        setToAccountId('')
        return
      }
      setCategory('Transfer')
      if (sib) {
        const outRow = d.merchant === 'Transfer out' ? d : sib
        const inRow = d.merchant === 'Transfer in' ? d : sib
        setFromAccountId(outRow.account_id != null ? String(outRow.account_id) : '')
        setToAccountId(inRow.account_id != null ? String(inRow.account_id) : '')
      } else if (d.merchant === 'Transfer out') {
        setFromAccountId(d.account_id != null ? String(d.account_id) : '')
        setToAccountId('')
      } else if (d.merchant === 'Transfer in') {
        setFromAccountId('')
        setToAccountId(d.account_id != null ? String(d.account_id) : '')
      } else {
        setFromAccountId(d.account_id != null ? String(d.account_id) : '')
        setToAccountId('')
      }
      return
    }
    setKind(d.transaction_type === 'credit' ? 'credit' : 'debit')
    setCategory(d.category)
    setMerchant(d.merchant ?? '')
    setPaymentMode(d.payment_mode)
    if (d.account_id != null) {
      setAccountId(String(d.account_id))
    } else if (d.account) {
      const match = accounts.find((a) => a.name === d.account)
      setAccountId(match ? String(match.id) : '')
    } else {
      setAccountId('')
    }
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [open, isEdit, editDraft, accounts])

  const applyTemplate = (t: TransactionTemplateOut) => {
    if (t.transaction_type === 'transfer') {
      setKind('transfer')
      setCategory('Transfer')
    } else if (t.transaction_type === 'credit') {
      setKind('credit')
    } else {
      setKind('debit')
    }
    if (t.amount != null) {
      setAmountRupees((t.amount / 100).toFixed(2))
    } else {
      setAmountRupees('')
    }
    setCategory(t.category || 'Other')
    setMerchant(t.merchant ?? '')
    setPaymentMode(t.payment_mode || 'UPI')
    if (t.account_id != null) {
      setAccountId(String(t.account_id))
      if (t.transaction_type === 'transfer') {
        setFromAccountId(String(t.account_id))
        setToAccountId('')
      }
    } else {
      setAccountId('')
      if (t.transaction_type === 'transfer') {
        setFromAccountId('')
        setToAccountId('')
      }
    }
    setNotes(t.notes ?? '')
    setTags(t.tags ?? '')
  }

  const createOne = useMutation({
    mutationFn: postManualTransaction,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['transactions'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-alerts'] })
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      onClose()
      setAmountRupees('')
      setMerchant('')
      setNotes('')
      setTags('')
    },
  })

  const createTransfer = useMutation({
    mutationFn: postTransfer,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['transactions'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-alerts'] })
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      onClose()
      setAmountRupees('')
      setNotes('')
      setTags('')
    },
  })

  const updateOne = useMutation({
    mutationFn: (p: {
      id: number
      body: {
        date: string
        amount_paise: number
        category?: string | null
        merchant?: string | null
        payment_mode?: string | null
        transaction_type?: 'debit' | 'credit' | null
        account_id?: number | null
        notes?: string | null
        tags?: string | null
        from_account_id?: number | null
        to_account_id?: number | null
      }
    }) => putTransaction(p.id, p.body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['transactions'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-alerts'] })
      void qc.invalidateQueries({ queryKey: ['budget-vs'] })
      onClose()
    },
  })

  /** Feedback loop: "always classify this way?" checkbox creates a merchant rule (which
   * retroactively re-applies to other matching transactions) alongside the edit save. */
  const createRuleMut = useMutation({
    mutationFn: postMerchantRule,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['merchant-rules'] })
    },
  })

  const activeAccounts = useMemo(() => accounts.filter((a) => a.is_active), [accounts])

  const categoryOptions = useMemo(() => {
    const base = [...MANUAL_TX_CATEGORIES]
    if (category && !base.includes(category as (typeof MANUAL_TX_CATEGORIES)[number])) {
      return [category, ...base]
    }
    return base
  }, [category])

  const paymentModeOptions = useMemo(() => {
    const base = [...PAYMENT_MODE_OPTIONS]
    if (paymentMode && !base.includes(paymentMode as (typeof PAYMENT_MODE_OPTIONS)[number])) {
      return [paymentMode, ...base]
    }
    return base
  }, [paymentMode])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const paise = rupeesToPaise(amountRupees)
    if (paise == null) return

    if (isEdit && transactionIdToEdit != null) {
      if (kind === 'transfer') {
        if (isOrphanTransferEdit) {
          const aid = accountId ? Number.parseInt(accountId, 10) : undefined
          updateOne.mutate({
            id: transactionIdToEdit,
            body: {
              date,
              amount_paise: paise,
              category,
              merchant: merchant.trim() || null,
              payment_mode: paymentMode,
              account_id: aid && !Number.isNaN(aid) ? aid : null,
              notes: notes.trim() || null,
              tags: tags.trim() || null,
            },
          })
          return
        }
        const from = Number.parseInt(fromAccountId, 10)
        const to = Number.parseInt(toAccountId, 10)
        if (!from || !to || from === to) return
        updateOne.mutate({
          id: transactionIdToEdit,
          body: {
            date,
            amount_paise: paise,
            from_account_id: from,
            to_account_id: to,
            notes: notes.trim() || null,
            tags: tags.trim() || null,
          },
        })
        return
      }
      const aid = accountId ? Number.parseInt(accountId, 10) : undefined
      const trimmedMerchant = merchant.trim()
      updateOne.mutate(
        {
          id: transactionIdToEdit,
          body: {
            date,
            amount_paise: paise,
            category,
            merchant: trimmedMerchant || null,
            payment_mode: paymentMode,
            transaction_type: kind,
            account_id: aid && !Number.isNaN(aid) ? aid : null,
            notes: notes.trim() || null,
            tags: tags.trim() || null,
          },
        },
        {
          onSuccess: () => {
            if (createRule && trimmedMerchant && category) {
              createRuleMut.mutate({
                match_type: ruleMatchType,
                match_value: trimmedMerchant,
                canonical_merchant: trimmedMerchant,
                merchant_type: null,
                category,
                source: 'user',
              })
            }
          },
        },
      )
      return
    }

    if (kind === 'transfer') {
      const from = Number.parseInt(fromAccountId, 10)
      const to = Number.parseInt(toAccountId, 10)
      if (!from || !to || from === to) return
      createTransfer.mutate({
        amount_paise: paise,
        from_account_id: from,
        to_account_id: to,
        date,
        notes: notes.trim() || null,
        tags: tags.trim() || null,
      })
      return
    }

    const aid = accountId ? Number.parseInt(accountId, 10) : undefined
    createOne.mutate({
      date,
      amount_paise: paise,
      category,
      merchant: merchant.trim() || null,
      payment_mode: paymentMode,
      transaction_type: kind,
      account_id: aid && !Number.isNaN(aid) ? aid : null,
      notes: notes.trim() || null,
      tags: tags.trim() || null,
      source: 'dashboard',
    })
  }

  const busy = createOne.isPending || createTransfer.isPending || updateOne.isPending
  const err = createOne.error ?? createTransfer.error ?? updateOne.error ?? null
  const transferSiblingMissing =
    isEdit &&
    Boolean(editDraft?.row.transfer_pair_id) &&
    editDraft?.row.transaction_type === 'transfer' &&
    editDraft.peer == null

  /** Import marked transfer but only one leg — edit category/merchant, not from/to pair. */
  const isOrphanTransferEdit =
    isEdit &&
    editDraft?.row.transaction_type === 'transfer' &&
    !editDraft?.row.transfer_pair_id

  const needsPairedTransferAccounts = kind === 'transfer' && !isOrphanTransferEdit

  /** Paired transfers already have two legs; other rows can switch type (e.g. debit → transfer). */
  const kindSwitchDisabled = isEdit && Boolean(editDraft?.row.transfer_pair_id)

  if (!open) {
    return null
  }

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-zinc-900/40"
        aria-label="Close"
        onClick={onClose}
      />
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-zinc-200 bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-3">
          <h2 className="text-lg font-semibold text-zinc-900">
            {isEdit ? 'Edit transaction' : 'Add transaction'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-sm text-zinc-500 hover:bg-zinc-100"
          >
            Close
          </button>
        </div>
        <form onSubmit={submit} className="flex flex-1 flex-col overflow-y-auto px-4 py-4">
          {transferSiblingMissing ? (
            <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
              The paired transfer leg is missing from the database. From/to accounts may be wrong
              until both legs exist; you can still edit amount, date, and notes.
            </p>
          ) : null}
          {!isEdit ? (
            <>
              <label className="mb-3 block text-sm">
                <span className="text-zinc-600">Apply template</span>
                <select
                  value={templateChoice}
                  onChange={(e) => {
                    const v = e.target.value
                    setTemplateChoice(v)
                    if (!v) return
                    const t = (templatesQ.data ?? []).find((x) => String(x.id) === v)
                    if (t) applyTemplate(t)
                  }}
                  className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  <option value="">— None —</option>
                  {(templatesQ.data ?? []).map((t) => (
                    <option key={t.id} value={String(t.id)}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              <p className="mb-3 text-xs text-zinc-500">
                Fills fields from a saved preset; you can edit before saving. Manage templates on{' '}
                <Link to="/transactions/templates" className="text-emerald-700 underline">
                  Transactions → Templates
                </Link>
                .
              </p>
            </>
          ) : null}

          <div className="mb-4 flex gap-2">
            {(['debit', 'credit', 'transfer'] as const).map((k) => (
              <button
                key={k}
                type="button"
                disabled={kindSwitchDisabled}
                onClick={() => {
                  setKind(k)
                  if (k === 'transfer' && isEdit && editDraft?.row.account_id != null) {
                    setFromAccountId(String(editDraft.row.account_id))
                  }
                }}
                className={`flex-1 rounded-lg border px-2 py-2 text-sm font-medium ${
                  kind === k
                    ? 'border-emerald-600 bg-emerald-50 text-emerald-900'
                    : 'border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50'
                } ${kindSwitchDisabled ? 'cursor-not-allowed opacity-60' : ''}`}
              >
                {k === 'debit' ? 'Debit' : k === 'credit' ? 'Credit' : 'Transfer'}
              </button>
            ))}
          </div>

          <label className="mb-3 block text-sm">
            <span className="text-zinc-600">Date</span>
            <input
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
            />
          </label>

          <label className="mb-3 block text-sm">
            <span className="text-zinc-600">Amount (₹)</span>
            <input
              required
              inputMode="decimal"
              value={amountRupees}
              onChange={(e) => setAmountRupees(e.target.value)}
              className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-right text-sm tabular-nums"
              placeholder="0.00"
            />
          </label>

          {needsPairedTransferAccounts ? (
            <>
              <label className="mb-3 block text-sm">
                <span className="text-zinc-600">From account</span>
                <select
                  required
                  value={fromAccountId}
                  onChange={(e) => setFromAccountId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  <option value="">— Select —</option>
                  {activeAccounts.map((a) => (
                    <option key={a.id} value={String(a.id)}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="mb-3 block text-sm">
                <span className="text-zinc-600">To account</span>
                <select
                  required
                  value={toAccountId}
                  onChange={(e) => setToAccountId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  <option value="">— Select —</option>
                  {activeAccounts.map((a) => (
                    <option key={a.id} value={String(a.id)}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <p className="mb-3 text-xs text-zinc-500">
                {isEdit && editDraft?.row.transfer_pair_id
                  ? 'Updates both legs of this internal transfer.'
                  : isEdit
                    ? 'Converts this row to a transfer and creates the matching credit leg.'
                    : 'Creates two linked rows excluded from spend totals and budgets.'}
              </p>
            </>
          ) : (
            <>
              <label className="mb-3 block text-sm">
                <span className="text-zinc-600">Category</span>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  {categoryOptions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="mb-3 block text-sm">
                <span className="text-zinc-600">Merchant / description</span>
                <input
                  value={merchant}
                  onChange={(e) => setMerchant(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                />
              </label>
              <label className="mb-3 block text-sm">
                <span className="text-zinc-600">Payment mode</span>
                <select
                  value={paymentMode}
                  onChange={(e) => setPaymentMode(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  {paymentModeOptions.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
              <label className="mb-3 block text-sm">
                <span className="text-zinc-600">Account</span>
                <select
                  value={accountId}
                  onChange={(e) => setAccountId(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
                >
                  <option value="">— Optional —</option>
                  {activeAccounts.map((a) => (
                    <option key={a.id} value={String(a.id)}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </label>
              {isEdit ? (
                <div className="mb-3 rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2">
                  <label className="flex items-center gap-2 text-sm text-zinc-700">
                    <input
                      type="checkbox"
                      checked={createRule}
                      onChange={(e) => setCreateRule(e.target.checked)}
                    />
                    Always classify this way?
                  </label>
                  {createRule ? (
                    <label className="mt-2 flex items-center gap-2 text-xs text-zinc-600">
                      Match
                      <select
                        value={ruleMatchType}
                        onChange={(e) =>
                          setRuleMatchType(e.target.value as 'exact' | 'contains')
                        }
                        className="rounded border border-zinc-200 px-1.5 py-1 text-xs"
                      >
                        <option value="exact">exactly</option>
                        <option value="contains">any merchant containing this text</option>
                      </select>
                    </label>
                  ) : null}
                </div>
              ) : null}
            </>
          )}

          <label className="mb-3 block text-sm">
            <span className="text-zinc-600">Notes</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
            />
          </label>
          <label className="mb-4 block text-sm">
            <span className="text-zinc-600">Tags (comma-separated)</span>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="goa, reimbursable"
              className="mt-1 w-full rounded-lg border border-zinc-200 px-3 py-2 text-sm"
            />
          </label>

          {err ? <p className="mb-3 text-sm text-red-600">{String(err)}</p> : null}

          <div className="mt-auto flex gap-2 border-t border-zinc-100 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-lg border border-zinc-200 py-2.5 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={
                busy ||
                (!isEdit && activeAccounts.length === 0) ||
                (needsPairedTransferAccounts && (!fromAccountId || !toAccountId))
              }
              className="flex-1 rounded-lg bg-emerald-700 py-2.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
            >
              {busy ? 'Saving…' : isEdit ? 'Save changes' : 'Save'}
            </button>
          </div>
          {!isEdit && activeAccounts.length === 0 ? (
            <p className="mt-2 text-xs text-amber-700">Add an account first on the Accounts page.</p>
          ) : null}
        </form>
      </div>
    </>
  )
}
