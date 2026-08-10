import { Check, RefreshCw } from 'lucide-react'

import type { DashboardAlerts } from '@/types/api'

export function AlertsBanner({
  data,
  onAck,
  ackingId,
}: {
  data: DashboardAlerts
  onAck?: (id: number) => void
  ackingId?: number | null
}) {
  if (data.alerts.length === 0) {
    return null
  }
  return (
    <div className="space-y-3">
      {data.alerts.map((alert, index) => {
        const canAck = alert.id != null && onAck != null
        const isAcking = canAck && ackingId === alert.id
        const severity = alert.severity.toLowerCase()
        const isError = severity === 'error' || severity === 'critical'
        const isWarning = severity === 'warning'

        const borderClass = isError
          ? 'border-red-200/80 from-red-50 to-red-50/30 text-red-950 shadow-red-900/5 ring-red-900/[0.04]'
          : isWarning
            ? 'border-amber-200/80 from-amber-50 to-amber-50/30 text-amber-950 shadow-amber-900/5 ring-amber-900/[0.04]'
            : 'border-blue-200/80 from-blue-50 to-blue-50/30 text-blue-950 shadow-blue-900/5 ring-blue-900/[0.04]'

        const dotClass = isError
          ? 'bg-red-500 shadow-red-600/40'
          : isWarning
            ? 'bg-amber-500 shadow-amber-600/40'
            : 'bg-blue-500 shadow-blue-600/40'

        const kindClass = isError ? 'text-red-900' : isWarning ? 'text-amber-900' : 'text-blue-900'
        const messageClass = isError ? 'text-red-800/90' : isWarning ? 'text-amber-800/90' : 'text-blue-800/90'

        return (
          <div
            key={alert.id ?? index}
            className={`flex items-start justify-between gap-3 rounded-xl border bg-gradient-to-r px-4 py-3.5 text-sm shadow-md ring-1 ${borderClass}`}
          >
            <div className="flex min-w-0 flex-1 gap-3">
              <span
                className={`mt-0.5 inline-flex h-2 w-2 shrink-0 rounded-full shadow-sm ${dotClass}`}
                aria-hidden
              />
              <p className="min-w-0">
                <span className={`font-semibold ${kindClass}`}>{alert.kind}</span>
                <span className={messageClass}>: {alert.message}</span>
              </p>
            </div>
            {canAck ? (
              <button
                type="button"
                onClick={() => onAck(alert.id!)}
                disabled={isAcking}
                className="flex shrink-0 items-center gap-1 rounded-lg border border-zinc-200/80 bg-white/80 px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-white disabled:opacity-50"
              >
                {isAcking ? (
                  <RefreshCw className="size-3.5 animate-spin" />
                ) : (
                  <Check className="size-3.5" />
                )}
                {isAcking ? 'Acking…' : 'Ack'}
              </button>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
