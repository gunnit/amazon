import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bell, AlertCircle, AlertTriangle, Info, Clock, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { alertsApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import { cn } from '@/lib/utils'
import {
  optimisticallyMarkAlertRead,
  optimisticallyMarkAllAlertsRead,
  restoreAlertQuerySnapshot,
  sortAlertsByPriority,
} from '@/lib/alertUtils'
import type { Alert } from '@/types'

function severityIcon(severity: string) {
  switch (severity) {
    case 'critical':
      return <AlertCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
    case 'warning':
      return <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0" />
    default:
      return <Info className="h-3.5 w-3.5 text-blue-500 shrink-0" />
  }
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'now'
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h`
  const days = Math.floor(hours / 24)
  return `${days}d`
}

function alertTypeLabel(alert: Alert, t: (key: string) => string): string | null {
  if (!alert.alert_type) return null

  const labels: Record<string, string> = {
    low_stock: t('alerts.type.low_stock'),
    sync_failure: t('alerts.type.sync_failure'),
    price_change: t('alerts.type.price_change'),
    bsr_drop: t('alerts.type.bsr_drop'),
    product_trend: t('alerts.type.product_trend'),
  }

  return labels[alert.alert_type] ?? alert.alert_type
}

function priorityAccent(severity: Alert['severity']): string {
  switch (severity) {
    case 'critical':
      return 'border-l-red-500'
    case 'warning':
      return 'border-l-amber-500'
    default:
      return 'border-l-blue-500'
  }
}

export function NotificationBell() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)

  const { data: unreadData } = useQuery({
    queryKey: ['unread-alert-count'],
    queryFn: alertsApi.getUnreadCount,
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
    staleTime: 30000,
    refetchOnWindowFocus: true,
  })

  const {
    data: recentAlerts = [],
    isLoading: isLoadingAlerts,
    isFetching: isRefreshingAlerts,
  } = useQuery({
    queryKey: ['recent-alerts'],
    queryFn: async () => {
      const response = await alertsApi.getAlerts({ status: 'unread', limit: 20 })
      return response.items
    },
    enabled: open,
    staleTime: 0,
    refetchOnMount: 'always',
  })

  const markReadMutation = useMutation({
    mutationFn: (id: string) => alertsApi.markAsRead(id),
    onMutate: async (id) => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: ['recent-alerts'] }),
        queryClient.cancelQueries({ queryKey: ['unread-alert-count'] }),
        queryClient.cancelQueries({ queryKey: ['alert-history'] }),
      ])

      return optimisticallyMarkAlertRead(queryClient, id)
    },
    onError: (_error, _id, snapshot) => {
      restoreAlertQuerySnapshot(queryClient, snapshot)
    },
    onSuccess: (response) => {
      queryClient.setQueryData(['unread-alert-count'], { count: response.unread_count })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['recent-alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alert-history'] })
    },
  })

  const markAllMutation = useMutation({
    mutationFn: () => alertsApi.markAllAsRead(),
    onMutate: async () => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: ['recent-alerts'] }),
        queryClient.cancelQueries({ queryKey: ['unread-alert-count'] }),
        queryClient.cancelQueries({ queryKey: ['alert-history'] }),
      ])

      return optimisticallyMarkAllAlertsRead(queryClient)
    },
    onError: (_error, _variables, snapshot) => {
      restoreAlertQuerySnapshot(queryClient, snapshot)
    },
    onSuccess: (response) => {
      queryClient.setQueryData(['unread-alert-count'], { count: response.unread_count })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['recent-alerts'] })
      queryClient.invalidateQueries({ queryKey: ['alert-history'] })
    },
  })

  const count = unreadData?.count ?? 0
  const prioritizedAlerts = useMemo(
    () => sortAlertsByPriority(recentAlerts).slice(0, 6),
    [recentAlerts]
  )

  const handleOpenAlert = (alert: Alert) => {
    if (!alert.is_read) {
      markReadMutation.mutate(alert.id)
    }

    setOpen(false)
    navigate('/alerts', { state: { focusAlertId: alert.id } })
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={t('notifications.title')}>
          <Bell className="h-5 w-5" />
          {count > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
              {count > 99 ? '99+' : count}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <span className="flex items-center gap-2 text-sm font-medium">
            {t('notifications.title')}
            {isRefreshingAlerts && !isLoadingAlerts && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </span>
          {count > 0 && (
            <button
              onClick={() => markAllMutation.mutate()}
              className="text-xs text-primary hover:underline disabled:pointer-events-none disabled:opacity-60"
              disabled={markAllMutation.isPending}
            >
              {markAllMutation.isPending && <Loader2 className="mr-1 inline h-3 w-3 animate-spin" />}
              {t('notifications.markAllRead')}
            </button>
          )}
        </div>

        <div className="max-h-[320px] overflow-y-auto">
          {isLoadingAlerts ? (
            <div className="space-y-3 px-4 py-3">
              {[0, 1, 2].map((item) => (
                <div key={item} className="rounded-lg border border-border/60 p-3">
                  <div className="mb-2 h-3 w-20 animate-pulse rounded bg-muted" />
                  <div className="mb-2 h-3 w-full animate-pulse rounded bg-muted" />
                  <div className="h-3 w-24 animate-pulse rounded bg-muted" />
                </div>
              ))}
            </div>
          ) : prioritizedAlerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Bell className="h-8 w-8 text-muted-foreground mb-2" />
              <p className="text-sm text-muted-foreground">{t('notifications.empty')}</p>
            </div>
          ) : (
            prioritizedAlerts.map((alert) => (
              <button
                key={alert.id}
                className={cn(
                  'flex w-full items-start gap-3 border-b border-l-2 px-4 py-3 text-left transition-colors hover:bg-muted/50 last:border-b-0',
                  priorityAccent(alert.severity)
                )}
                onClick={() => handleOpenAlert(alert)}
              >
                <div className="mt-0.5">{severityIcon(alert.severity)}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {alertTypeLabel(alert, t) && (
                      <span className="truncate text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                        {alertTypeLabel(alert, t)}
                      </span>
                    )}
                    {alert.asin && (
                      <span className="truncate text-[11px] text-muted-foreground">
                        {alert.asin}
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm leading-snug line-clamp-2">{alert.message}</p>
                  <span className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {timeAgo(alert.triggered_at)}
                    {alert.rule_name && <span className="truncate">{alert.rule_name}</span>}
                  </span>
                </div>
                <div className="mt-1 shrink-0">
                  {markReadMutation.isPending && markReadMutation.variables === alert.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                  ) : (
                    <span className="block h-2 w-2 rounded-full bg-primary" />
                  )}
                </div>
              </button>
            ))
          )}
        </div>

        <div className="border-t px-4 py-2.5">
          <button
            onClick={() => {
              setOpen(false)
              navigate('/alerts')
            }}
            className="text-xs text-primary hover:underline w-full text-center"
          >
            {t('notifications.viewAll')}
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
