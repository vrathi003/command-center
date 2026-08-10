import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Check, Inbox, RefreshCw } from 'lucide-react'
import { useState } from 'react'

import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { ackAlert, fetchAlerts } from '@/lib/api'
import type { AlertNotification } from '@/types/api'

type StatusFilter = 'unread' | 'acked' | 'all'

function formatAlertDate(value: string): string {
  try {
    return new Date(value).toLocaleString('en-IN', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

function SeverityBadge({ severity }: { severity: string }) {
  const normalized = severity.toLowerCase()
  const styles =
    normalized === 'error' || normalized === 'critical'
      ? 'bg-red-50 text-red-700'
      : normalized === 'warning' || normalized === 'warn'
        ? 'bg-amber-50 text-amber-700'
        : 'bg-blue-50 text-blue-700'
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${styles}`}>
      {severity}
    </span>
  )
}

function AlertRow({
  alert,
  onAck,
  ackingId,
}: {
  alert: AlertNotification
  onAck: (id: number) => void
  ackingId: number | null
}) {
  const isUnread = alert.status === 'unread'
  const isAcking = ackingId === alert.id

  return (
    <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium text-zinc-900">{alert.title || alert.kind}</p>
          <SeverityBadge severity={alert.severity} />
          {!isUnread ? (
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-600">
              Acked
            </span>
          ) : null}
        </div>
        <p className="text-sm text-zinc-600">{alert.message}</p>
        <p className="text-xs text-zinc-400">
          {formatAlertDate(alert.created_at)}
          {alert.acked_at ? ` · Acked ${formatAlertDate(alert.acked_at)}` : ''}
        </p>
      </div>
      {isUnread ? (
        <button
          type="button"
          onClick={() => onAck(alert.id)}
          disabled={isAcking}
          className="flex shrink-0 items-center gap-1.5 self-start rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 disabled:opacity-50"
        >
          {isAcking ? <RefreshCw className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
          {isAcking ? 'Acking…' : 'Ack'}
        </button>
      ) : null}
    </div>
  )
}

export function AlertsPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('unread')
  const [ackingId, setAckingId] = useState<number | null>(null)

  const alertsQ = useQuery({
    queryKey: ['alerts', statusFilter],
    queryFn: () => fetchAlerts(statusFilter),
  })

  function invalidateAlerts() {
    void queryClient.invalidateQueries({ queryKey: ['alerts'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard-alerts'] })
  }

  const ackMutation = useMutation({
    mutationFn: ackAlert,
    onMutate: (id) => setAckingId(id),
    onSettled: () => setAckingId(null),
    onSuccess: invalidateAlerts,
  })

  const alerts = alertsQ.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        eyebrow="Operations"
        title="Alerts"
        description="In-app notifications from budget thresholds, due dates, and background checks."
        actions={
          <button
            type="button"
            onClick={() => void alertsQ.refetch()}
            disabled={alertsQ.isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 shadow-sm hover:bg-zinc-50 disabled:opacity-50"
          >
            <RefreshCw className={['size-3.5', alertsQ.isFetching ? 'animate-spin' : ''].join(' ')} />
            Refresh
          </button>
        }
      />

      {alertsQ.isPending ? (
        <PageLoading />
      ) : alertsQ.isError ? (
        <PageError
          title="Failed to load alerts"
          message="Could not fetch alert notifications. Check that the API is running."
        />
      ) : (
        <Panel className="overflow-hidden p-0">
          <div className="flex flex-wrap gap-2 border-b border-zinc-100 px-4 py-3">
            {(
              [
                ['unread', 'Unread'],
                ['acked', 'Acked'],
                ['all', 'All'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setStatusFilter(value)}
                className={[
                  'rounded-full px-3 py-1 text-xs font-medium transition',
                  statusFilter === value
                    ? 'bg-emerald-100 text-emerald-900'
                    : 'bg-zinc-100 text-zinc-600 hover:bg-zinc-200',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          </div>

          {alerts.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              {statusFilter === 'unread' ? (
                <>
                  <Inbox className="size-8 text-emerald-600" />
                  <p className="text-sm font-medium text-zinc-700">No unread alerts.</p>
                  <p className="text-sm text-zinc-400">New notifications will appear here.</p>
                </>
              ) : (
                <>
                  <Bell className="size-8 text-zinc-400" />
                  <p className="text-sm font-medium text-zinc-700">No alerts match this filter.</p>
                </>
              )}
            </div>
          ) : (
            <div className="divide-y divide-zinc-100">
              {alerts.map((alert) => (
                <AlertRow
                  key={alert.id}
                  alert={alert}
                  onAck={(id) => ackMutation.mutate(id)}
                  ackingId={ackingId}
                />
              ))}
            </div>
          )}

          {ackMutation.isError ? (
            <p className="border-t border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
              {(ackMutation.error as Error).message}
            </p>
          ) : null}
        </Panel>
      )}
    </div>
  )
}
