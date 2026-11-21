import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Play } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { TabProps } from '@/components/catalog/types'

const POLL_MS = 5000

const scanKey = (accountId: string) => ['catalog-monitor', 'scan', accountId]

export function ScanButton({ accountId, t, toast }: Pick<TabProps, 'accountId' | 't' | 'toast'>) {
  const queryClient = useQueryClient()

  // Poll the scan state every 5 s, but only while a scan is running.
  const scanQuery = useQuery({
    queryKey: scanKey(accountId),
    queryFn: () => catalogMonitorApi.getScan(accountId),
    enabled: !!accountId,
    refetchInterval: (query) => (query.state.data?.running ? POLL_MS : false),
  })
  const running = scanQuery.data?.running === true

  // When a scan that we saw running ends, reload the matrix.
  const wasRunning = useRef(false)
  useEffect(() => {
    if (wasRunning.current && !running) {
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', 'quality'] })
      const summary = scanQuery.data?.summary
      toast({
        title: t('cm.scan.done'),
        description: t('cm.scan.doneDetail', {
          scanned: summary?.scanned ?? 0,
          failed: summary?.failed ?? 0,
        }),
        variant: summary && (summary.failed ?? 0) > 0 ? 'destructive' : 'default',
      })
    }
    wasRunning.current = running
  }, [running, scanQuery.data, queryClient, toast, t])

  const start = useMutation({
    mutationFn: () => catalogMonitorApi.startScan(accountId),
    onSuccess: (res) => {
      if (!res.started) toast({ title: t('cm.scan.alreadyRunning') })
      void queryClient.invalidateQueries({ queryKey: scanKey(accountId) })
    },
    onError: (error) =>
      toast({
        title: t('cm.scan.startError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  return (
    <Button onClick={() => start.mutate()} disabled={!accountId || running || start.isPending}>
      {running || start.isPending ? (
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      ) : (
        <Play className="mr-2 h-4 w-4" />
      )}
      {running ? t('cm.scan.running') : t('cm.scan.start')}
    </Button>
  )
}
