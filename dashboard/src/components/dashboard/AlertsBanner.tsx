import type { DashboardAlerts } from '@/types/api'

export function AlertsBanner({ data }: { data: DashboardAlerts }) {
  if (data.alerts.length === 0) {
    return null
  }
  return (
    <div className="space-y-3">
      {data.alerts.map((a, i) => (
        <div
          key={i}
          className="flex gap-3 rounded-xl border border-amber-200/80 bg-gradient-to-r from-amber-50 to-amber-50/30 px-4 py-3.5 text-sm text-amber-950 shadow-md shadow-amber-900/5 ring-1 ring-amber-900/[0.04]"
        >
          <span
            className="mt-0.5 inline-flex h-2 w-2 shrink-0 rounded-full bg-amber-500 shadow-sm shadow-amber-600/40"
            aria-hidden
          />
          <p>
            <span className="font-semibold text-amber-900">{a.kind}</span>
            <span className="text-amber-800/90">: {a.message}</span>
          </p>
        </div>
      ))}
    </div>
  )
}
