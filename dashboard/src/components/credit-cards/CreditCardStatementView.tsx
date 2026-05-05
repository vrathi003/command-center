import { formatPaise, formatPaiseCompact } from '@/lib/format'
import type { CreditCardStatementOut } from '@/types/api'

function formatSummaryEntry(key: string, val: unknown): string {
  if (typeof val === 'number' && key.endsWith('_paise')) {
    return formatPaiseCompact(val)
  }
  if (val === null || val === undefined) {
    return '—'
  }
  return String(val)
}

export function CreditCardStatementView({ s }: { s: CreditCardStatementOut }) {
  const summaryEntries = Object.entries(s.summary ?? {})

  return (
    <div className="space-y-4">
      {summaryEntries.length > 0 ? (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">Parsed summary</p>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            {summaryEntries.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-b border-zinc-50 py-1">
                <dt className="text-zinc-500">{k.replace(/_/g, ' ')}</dt>
                <dd className="tabular-nums text-zinc-900">{formatSummaryEntry(k, v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">No summary fields detected from this file.</p>
      )}

      {s.line_items.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-zinc-200">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Description</th>
                <th className="px-3 py-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {s.line_items.map((row, i) => {
                const ap = row.amount_paise
                const amt = typeof ap === 'number' ? formatPaise(ap) : '—'
                return (
                  <tr key={i}>
                    <td className="px-3 py-1.5 tabular-nums text-zinc-700">{String(row.date ?? '')}</td>
                    <td className="px-3 py-1.5 text-zinc-800">{String(row.description ?? '')}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-zinc-900">{amt}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-amber-800">
          No transaction lines parsed. Try a CSV export with date, amount, and category columns, or another
          PDF layout.
        </p>
      )}

      {s.extraction_preview ? (
        <details className="rounded-lg border border-zinc-200 bg-zinc-50/50 p-3 text-sm">
          <summary className="cursor-pointer font-medium text-zinc-800">Raw text preview</summary>
          <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs text-zinc-600">
            {s.extraction_preview}
          </pre>
        </details>
      ) : null}
    </div>
  )
}
