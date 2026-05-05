import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { CreditCardStatementView } from '@/components/credit-cards/CreditCardStatementView'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import {
  applyCreditCardStatement,
  deleteCreditCardStatement,
  fetchCreditCard,
  fetchCreditCardStatement,
} from '@/lib/api'
import { formatPaiseCompact } from '@/lib/format'


function statementLineTotal(s: { line_items: Array<{ amount_paise?: unknown }> }): number {
  return s.line_items.reduce((sum, row) => {
    const ap = row.amount_paise
    return sum + (typeof ap === 'number' ? ap : 0)
  }, 0)
}

export function CreditCardStatementPage() {
  const { cardId: cardIdParam, statementId: statementIdParam } = useParams<{
    cardId: string
    statementId: string
  }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const cardId = Number.parseInt(cardIdParam ?? '', 10)
  const statementId = Number.parseInt(statementIdParam ?? '', 10)

  const card = useQuery({
    queryKey: ['credit-card', cardId],
    queryFn: () => fetchCreditCard(cardId),
    enabled: Number.isFinite(cardId) && cardId > 0,
  })

  const statement = useQuery({
    queryKey: ['credit-card-statement', cardId, statementId],
    queryFn: () => fetchCreditCardStatement(cardId, statementId),
    enabled: Number.isFinite(cardId) && cardId > 0 && Number.isFinite(statementId) && statementId > 0,
  })

  const applyStmt = useMutation({
    mutationFn: () => applyCreditCardStatement(cardId, statementId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['credit-card-statement', cardId, statementId] })
      void qc.invalidateQueries({ queryKey: ['credit-card-statements', cardId] })
      void qc.invalidateQueries({ queryKey: ['credit-card', cardId] })
      void qc.invalidateQueries({ queryKey: ['credit-cards'] })
      void qc.invalidateQueries({ queryKey: ['transactions'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-summary'] })
    },
  })

  const delStmt = useMutation({
    mutationFn: () => deleteCreditCardStatement(cardId, statementId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['credit-card-statements', cardId] })
      void qc.invalidateQueries({ queryKey: ['credit-card', cardId] })
      void qc.invalidateQueries({ queryKey: ['credit-cards'] })
    },
  })

  if (!Number.isFinite(cardId) || cardId <= 0 || !Number.isFinite(statementId) || statementId <= 0) {
    return <PageError title="Invalid link" message={<p className="text-sm">Check the URL.</p>} />
  }

  if (card.isPending || statement.isPending) {
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
              All credit cards
            </Link>
          </p>
        }
      />
    )
  }

  if (statement.isError || !statement.data) {
    return (
      <PageError
        title="Statement not found"
        message={
          <p className="text-sm">
            {String(statement.error ?? '')}{' '}
            <Link to={`/credit-cards/${cardId}`} className="text-emerald-800 underline">
              Back to card
            </Link>
          </p>
        }
      />
    )
  }

  const c = card.data
  const s = statement.data
  const canApply = s.status === 'pending_review' && s.line_items.length > 0
  const lineTotal = statementLineTotal(s)

  return (
    <div className="space-y-8">
      <div>
        <Link
          to={`/credit-cards/${cardId}`}
          className="text-xs font-medium text-emerald-700 hover:underline"
        >
          ← {c.name}
        </Link>
        <PageHero
          eyebrow="Statement"
          title={s.filename}
          description={
            <>
              {s.period_start && s.period_end ? `${s.period_start} → ${s.period_end}` : 'Period not detected'}
              {s.created_at ? ` · uploaded ${s.created_at}` : ''}
          ·{' '}
              <span
                className={
                  s.status === 'applied' ? 'text-emerald-800' : 'text-amber-800'
                }
              >
                {s.status}
              </span>
              {lineTotal > 0 ? (
                <>
                  {' '}
                  · Total parsed lines {formatPaiseCompact(lineTotal)}
                </>
              ) : null}
            </>
          }
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {canApply ? (
          <button
            type="button"
            disabled={applyStmt.isPending}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-800 disabled:opacity-50"
            onClick={() => applyStmt.mutate()}
          >
            {applyStmt.isPending ? 'Importing…' : 'Import to transactions'}
          </button>
        ) : null}
        <button
          type="button"
          disabled={delStmt.isPending}
          className="rounded-lg border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-800 shadow-sm hover:bg-red-50 disabled:opacity-50"
          onClick={() => {
            if (window.confirm('Remove this statement record?')) {
              delStmt.mutate(undefined, {
                onSuccess: () => navigate(`/credit-cards/${cardId}`),
              })
            }
          }}
        >
          Remove statement
        </button>
      </div>
      {applyStmt.isError ? <p className="text-sm text-red-600">{String(applyStmt.error)}</p> : null}
      {delStmt.isError ? <p className="text-sm text-red-600">{String(delStmt.error)}</p> : null}

      <Panel>
        <CreditCardStatementView s={s} />
      </Panel>
    </div>
  )
}
