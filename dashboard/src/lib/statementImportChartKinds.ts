import type { StatementImportTransactionRow } from '@/types/api'

/** Max ₹ difference when pairing a refund to an expense (discount rounding). */
export const REFUND_MATCH_TOLERANCE_INR = 15

export type ChartKindRow = {
  id: string
  kind: string
  amount: number
}

function txKind(t: StatementImportTransactionRow): string {
  return (t.tx_kind ?? 'spend').toLowerCase()
}

function amountsMatch(spendAmount: number, refundAmount: number): boolean {
  const diff = Math.abs(Math.abs(spendAmount) - Math.abs(refundAmount))
  return diff <= REFUND_MATCH_TOLERANCE_INR
}

function matchScore(
  spend: StatementImportTransactionRow,
  refund: StatementImportTransactionRow,
): number {
  const diff = Math.abs(Math.abs(spend.amount) - Math.abs(refund.amount))
  const samePeriod = spend.statement_period === refund.statement_period ? 0 : 1
  const dateOk = spend.date <= refund.date ? 0 : 1
  return samePeriod * 1000 + dateOk * 100 + diff
}

/**
 * Prepare rows for type charts:
 * - Matched refund + expense pairs are excluded (netted off).
 * - Unmatched refunds are treated as bill paid.
 * - Refund is never a chart category.
 */
export function resolveChartKindRows(
  rows: StatementImportTransactionRow[],
): ChartKindRow[] {
  const spends = rows.filter((t) => txKind(t) === 'spend')
  const refunds = rows.filter((t) => txKind(t) === 'refund')
  const others = rows.filter((t) => {
    const k = txKind(t)
    return k !== 'spend' && k !== 'refund'
  })

  const usedSpendIds = new Set<string>()
  const offsetRefundIds = new Set<string>()

  for (const refund of refunds) {
    let best: { spend: StatementImportTransactionRow; score: number } | null = null
    for (const spend of spends) {
      if (usedSpendIds.has(spend.id)) continue
      if (spend.bank !== refund.bank || spend.card !== refund.card) continue
      if (!amountsMatch(spend.amount, refund.amount)) continue
      const score = matchScore(spend, refund)
      if (!best || score < best.score) {
        best = { spend, score }
      }
    }
    if (best) {
      usedSpendIds.add(best.spend.id)
      offsetRefundIds.add(refund.id)
    }
  }

  const result: ChartKindRow[] = []

  for (const t of spends) {
    if (usedSpendIds.has(t.id)) continue
    result.push({ id: t.id, kind: 'spend', amount: Math.abs(t.amount) })
  }

  for (const t of refunds) {
    if (offsetRefundIds.has(t.id)) continue
    result.push({ id: t.id, kind: 'payment', amount: Math.abs(t.amount) })
  }

  for (const t of others) {
    result.push({ id: t.id, kind: txKind(t), amount: Math.abs(t.amount) })
  }

  return result
}

export function aggregateChartKindsByType(
  rows: StatementImportTransactionRow[],
): Record<string, { count: number; amount: number }> {
  const sums: Record<string, { count: number; amount: number }> = {}
  for (const row of resolveChartKindRows(rows)) {
    if (!sums[row.kind]) sums[row.kind] = { count: 0, amount: 0 }
    sums[row.kind].count += 1
    sums[row.kind].amount += row.amount
  }
  return sums
}
