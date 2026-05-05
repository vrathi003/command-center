import type { CreditCardStatementOut } from '@/types/api'

export type StatementGranularity = 'month' | 'quarter' | 'year'

export type StatementPeriodBucket = {
  key: string
  label: string
  total_paise: number
  line_count: number
  statement_count: number
  by_category_paise: Record<string, number>
}

function parseIsoDate(raw: string | null | undefined): Date | null {
  if (raw == null || typeof raw !== 'string') {
    return null
  }
  const s = raw.trim().slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    return null
  }
  const d = new Date(`${s}T12:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Best-effort parse for bank exports (ISO, or strings Date can interpret). */
function parseFlexibleDate(raw: string | null | undefined): Date | null {
  if (raw == null || typeof raw !== 'string') {
    return null
  }
  const t = raw.trim()
  if (!t) {
    return null
  }
  const iso = parseIsoDate(t)
  if (iso) {
    return iso
  }
  const d = new Date(t)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Statement-level anchor when line dates are missing. */
export function getStatementRefDate(s: CreditCardStatementOut): Date | null {
  const pe = parseIsoDate(s.period_end)
  if (pe) {
    return pe
  }
  let max: Date | null = null
  for (const row of s.line_items) {
    const d = parseFlexibleDate(String(row.date ?? ''))
    if (d && (!max || d > max)) {
      max = d
    }
  }
  if (max) {
    return max
  }
  const ca = s.created_at
  if (typeof ca === 'string' && ca.length >= 10) {
    return parseIsoDate(ca.slice(0, 10))
  }
  return null
}

function lineBucketDate(
  row: Record<string, unknown>,
  statement: CreditCardStatementOut,
): Date | null {
  const fromLine = parseFlexibleDate(String(row.date ?? ''))
  if (fromLine) {
    return fromLine
  }
  return getStatementRefDate(statement)
}

function bucketKey(d: Date, g: StatementGranularity): string {
  const y = d.getFullYear()
  const m = d.getMonth()
  if (g === 'year') {
    return `${y}`
  }
  if (g === 'quarter') {
    const q = Math.floor(m / 3) + 1
    return `${y}-Q${q}`
  }
  return `${y}-${String(m + 1).padStart(2, '0')}`
}

function bucketLabel(key: string, g: StatementGranularity): string {
  if (g === 'year') {
    return key
  }
  if (g === 'quarter') {
    const [y, qpart] = key.split('-Q')
    return qpart ? `Q${qpart} ${y}` : key
  }
  const [y, mo] = key.split('-')
  const mi = Number.parseInt(mo ?? '1', 10) - 1
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const label = months[mi] ?? mo
  return `${label} ${y}`
}

function categoryLabel(row: Record<string, unknown>): string {
  const c = row.category
  if (typeof c === 'string' && c.trim()) {
    return c.trim()
  }
  return 'Uncategorised'
}

function lineAmountPaise(row: Record<string, unknown>): number {
  const ap = row.amount_paise
  return typeof ap === 'number' && ap > 0 ? ap : 0
}

/**
 * Aggregates parsed line items across all statements by calendar month / quarter / year
 * (using each line’s date, or the statement period if missing).
 */
export function aggregateStatementLineItems(
  statements: CreditCardStatementOut[],
  granularity: StatementGranularity,
): StatementPeriodBucket[] {
  const map = new Map<
    string,
    {
      total_paise: number
      line_count: number
      stmts: Set<number>
      by_category_paise: Record<string, number>
    }
  >()

  for (const s of statements) {
    if (!s.line_items.length) {
      continue
    }
    for (const raw of s.line_items) {
      const row = raw as Record<string, unknown>
      const d = lineBucketDate(row, s)
      if (!d) {
        continue
      }
      const key = bucketKey(d, granularity)
      const amt = lineAmountPaise(row)
      if (amt <= 0) {
        continue
      }
      const cat = categoryLabel(row)
      let b = map.get(key)
      if (!b) {
        b = { total_paise: 0, line_count: 0, stmts: new Set<number>(), by_category_paise: {} }
        map.set(key, b)
      }
      b.total_paise += amt
      b.line_count += 1
      b.stmts.add(s.id)
      b.by_category_paise[cat] = (b.by_category_paise[cat] ?? 0) + amt
    }
  }

  const rows: StatementPeriodBucket[] = [...map.entries()]
    .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([key, v]) => ({
      key,
      label: bucketLabel(key, granularity),
      total_paise: v.total_paise,
      line_count: v.line_count,
      statement_count: v.stmts.size,
      by_category_paise: v.by_category_paise,
    }))

  return rows
}
