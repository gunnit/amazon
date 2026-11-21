import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ImageOff, Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { TabProps } from '@/components/catalog/types'
import { TrafficLight } from './TrafficLight'
import { describeResult, ruleLabel, stateLabel } from './describe'

interface Props extends Pick<TabProps, 'accountId' | 't' | 'toast'> {
  asin: string | null
  onClose: () => void
}

export function QualityDetailDialog({ accountId, asin, onClose, t, toast }: Props) {
  const queryClient = useQueryClient()
  const [imageFailed, setImageFailed] = useState(false)
  const [keyword, setKeyword] = useState('')

  const query = useQuery({
    queryKey: ['catalog-monitor', 'quality-detail', accountId, asin],
    queryFn: () => catalogMonitorApi.getQualityDetail(accountId, asin as string),
    enabled: !!asin && !!accountId,
  })
  const detail = query.data

  useEffect(() => {
    setImageFailed(false)
    setKeyword(detail?.main_keyword ?? '')
  }, [asin, detail?.main_keyword, detail?.main_image_url])

  const save = useMutation({
    mutationFn: () => catalogMonitorApi.putKeyword(accountId, asin as string, keyword.trim()),
    onSuccess: () => {
      toast({ title: t('cm.detail.keywordSaved') })
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', 'quality-detail'] })
    },
    onError: (error) =>
      toast({
        title: t('cm.detail.keywordError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const sourceLabel = (source: string) => {
    const key = `cm.detail.source.${source}`
    const text = t(key)
    return text === key ? source : text
  }

  const keywordChanged = keyword.trim() !== (detail?.main_keyword ?? '')

  return (
    <Dialog open={asin !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="pr-6">{detail?.title ?? asin}</DialogTitle>
          <DialogDescription className="font-mono">
            {asin}
            {detail?.sku ? ` · ${detail.sku}` : ''}
          </DialogDescription>
        </DialogHeader>

        {query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
        {query.isError && <p className="text-sm text-destructive">{t('cm.detail.loadError')}</p>}

        {detail && (
          <div className="space-y-5">
            <div className="flex flex-wrap gap-4">
              <div className="flex h-40 w-40 shrink-0 items-center justify-center rounded-md border bg-white">
                {detail.main_image_url && !imageFailed ? (
                  <img
                    src={detail.main_image_url}
                    alt={detail.title ?? detail.asin}
                    referrerPolicy="no-referrer"
                    onError={() => setImageFailed(true)}
                    className="max-h-full max-w-full object-contain"
                  />
                ) : (
                  <span className="flex flex-col items-center gap-1 text-xs text-muted-foreground">
                    <ImageOff className="h-6 w-6" aria-hidden="true" />
                    {t('cm.detail.noImage')}
                  </span>
                )}
              </div>
              <div className="min-w-[220px] flex-1 space-y-3">
                <div className="flex items-center gap-3">
                  <TrafficLight
                    state={detail.state}
                    size="lg"
                    label={`${t('cm.quality.col.overall')}: ${stateLabel(t, detail.state)}`}
                  />
                  <div>
                    <div className="text-sm font-medium">{stateLabel(t, detail.state)}</div>
                    <div className="text-xs text-muted-foreground">
                      {t('cm.detail.score', { score: detail.score })}
                    </div>
                  </div>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="cm-main-keyword">{t('cm.detail.mainKeyword')}</Label>
                  <div className="flex gap-2">
                    <Input
                      id="cm-main-keyword"
                      value={keyword}
                      maxLength={255}
                      placeholder={t('cm.detail.keywordPlaceholder')}
                      onChange={(e) => setKeyword(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && keywordChanged && !save.isPending) save.mutate()
                      }}
                    />
                    <Button
                      onClick={() => save.mutate()}
                      disabled={!keywordChanged || save.isPending}
                    >
                      {save.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                      {t('common.save')}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {detail.main_keyword_source
                      ? t('cm.detail.keywordSource', {
                          source: sourceLabel(detail.main_keyword_source),
                        })
                      : t('cm.detail.keywordNone')}{' '}
                    {t('cm.detail.keywordNextScan')}
                  </p>
                </div>
              </div>
            </div>

            <ul className="divide-y rounded-md border">
              {detail.results.length === 0 && (
                <li className="p-3 text-sm text-muted-foreground">{t('cm.detail.noResults')}</li>
              )}
              {detail.results.map((r) => {
                const d = describeResult(t, r)
                return (
                  <li key={r.key} className="flex gap-3 p-3">
                    <TrafficLight
                      state={r.state}
                      label={`${ruleLabel(t, r.key)}: ${stateLabel(t, r.state)}`}
                      className="mt-0.5"
                    />
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">{ruleLabel(t, r.key)}</span>
                        <Badge variant={r.mandatory ? 'default' : 'outline'} className="text-[10px]">
                          {r.mandatory ? t('cm.tag.mandatory') : t('cm.tag.bestPractice')}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{stateLabel(t, r.state)}</span>
                      </div>
                      {d.messages.map((m, i) => (
                        <p key={i} className="text-sm">
                          {m}
                        </p>
                      ))}
                      {d.measured.length > 0 && (
                        <dl className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                          {d.measured.map((m) => (
                            <div key={m.label} className="flex gap-1">
                              <dt>{m.label}:</dt>
                              <dd className="font-medium text-foreground">{m.value}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                      {d.notes.map((n, i) => (
                        <p key={i} className="text-xs italic text-muted-foreground">
                          {n}
                        </p>
                      ))}
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
