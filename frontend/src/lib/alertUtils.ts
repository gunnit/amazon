import type { QueryClient, QueryKey } from '@tanstack/react-query'
import type { Alert, AlertListResponse } from '@/types'

const SEVERITY_ORDER: Record<Alert['severity'], number> = {
  critical: 0,
  warning: 1,
  info: 2,
}

type AlertHistorySnapshot = [QueryKey, AlertListResponse | undefined]

export interface AlertQuerySnapshot {
  unreadCount: { count: number } | undefined
  recentAlerts: AlertListResponse | undefined
  alertHistory: AlertHistorySnapshot[]
}

export function sortAlertsByPriority(alerts: Alert[]): Alert[] {
  return [...alerts].sort((left, right) => {
    const severityDelta = SEVERITY_ORDER[left.severity] - SEVERITY_ORDER[right.severity]
    if (severityDelta !== 0) return severityDelta

    return new Date(right.triggered_at).getTime() - new Date(left.triggered_at).getTime()
  })
}

function updateAlertHistoryCaches(
  queryClient: QueryClient,
  updater: (response: AlertListResponse, queryKey: QueryKey) => AlertListResponse
) {
  for (const [queryKey, response] of queryClient.getQueriesData<AlertListResponse>({
    queryKey: ['alert-history'],
  })) {
    if (!response) continue
    queryClient.setQueryData<AlertListResponse>(queryKey, updater(response, queryKey))
  }
}

export function optimisticallyMarkAlertRead(
  queryClient: QueryClient,
  alertId: string
): AlertQuerySnapshot {
  const snapshot: AlertQuerySnapshot = {
    unreadCount: queryClient.getQueryData<{ count: number }>(['unread-alert-count']),
    recentAlerts: queryClient.getQueryData<AlertListResponse>(['recent-alerts']),
    alertHistory: queryClient.getQueriesData<AlertListResponse>({ queryKey: ['alert-history'] }),
  }

  queryClient.setQueryData<{ count: number }>(['unread-alert-count'], (current) => {
    if (!current) return current
    return { count: Math.max(0, current.count - 1) }
  })

  queryClient.setQueryData<AlertListResponse>(['recent-alerts'], (current) =>
    current
      ? {
          ...current,
          items: current.items.filter((alert) => alert.id !== alertId),
          total: Math.max(0, current.total - 1),
          has_more: current.offset + Math.max(0, current.total - 1) > current.limit,
        }
      : current
  )

  updateAlertHistoryCaches(queryClient, (response, queryKey) => {
    const params = (queryKey[1] as { status?: string } | undefined) ?? {}
    if (params.status === 'unread') {
      const nextItems = response.items.filter((alert) => alert.id !== alertId)
      return {
        ...response,
        items: nextItems,
        total: Math.max(0, response.total - (nextItems.length === response.items.length ? 0 : 1)),
        has_more: response.offset + nextItems.length < Math.max(0, response.total - 1),
      }
    }

    return {
      ...response,
      items: response.items.map((alert) =>
        alert.id === alertId
          ? {
              ...alert,
              is_read: true,
            }
          : alert
      ),
    }
  })

  return snapshot
}

export function optimisticallyMarkAllAlertsRead(
  queryClient: QueryClient
): AlertQuerySnapshot {
  const snapshot: AlertQuerySnapshot = {
    unreadCount: queryClient.getQueryData<{ count: number }>(['unread-alert-count']),
    recentAlerts: queryClient.getQueryData<AlertListResponse>(['recent-alerts']),
    alertHistory: queryClient.getQueriesData<AlertListResponse>({ queryKey: ['alert-history'] }),
  }

  queryClient.setQueryData<{ count: number }>(['unread-alert-count'], (current) =>
    current ? { count: 0 } : current
  )
  queryClient.setQueryData<AlertListResponse>(['recent-alerts'], (current) =>
    current
      ? {
          ...current,
          items: [],
          total: 0,
          has_more: false,
        }
      : current
  )

  updateAlertHistoryCaches(queryClient, (response, queryKey) => {
    const params = (queryKey[1] as { status?: string } | undefined) ?? {}
    if (params.status === 'unread') {
      return {
        ...response,
        items: [],
        total: 0,
        has_more: false,
      }
    }

    return {
      ...response,
      items: response.items.map((alert) => ({
        ...alert,
        is_read: true,
      })),
    }
  })

  return snapshot
}

export function restoreAlertQuerySnapshot(
  queryClient: QueryClient,
  snapshot: AlertQuerySnapshot | undefined
) {
  if (!snapshot) return

  queryClient.setQueryData(['unread-alert-count'], snapshot.unreadCount)
  queryClient.setQueryData(['recent-alerts'], snapshot.recentAlerts)

  for (const [queryKey, alerts] of snapshot.alertHistory) {
    queryClient.setQueryData(queryKey, alerts)
  }
}
