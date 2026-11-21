import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { BaselineUploadResponse, BulkUploadMode, BulkUploadResponse } from '@/types'
import { AccountPicker } from '@/components/catalog/AccountPicker'
import type { TabProps } from '@/components/catalog/types'
import { saveBlob, today } from './download'
import { FilePicker } from './FilePicker'
import { NewItemsSection } from './NewItemsSection'
import { BaselineResult, UploadResult } from './UploadResult'
import { useIsAdmin } from './useIsAdmin'

interface Props extends TabProps {
  onOpenApprovals: (batchId?: string | null) => void
}

function Step({ n, title, text, children }: { n: number; title: string; text: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden="true"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
      >
        {n}
      </span>
      <div className="min-w-0 flex-1 space-y-3">
        <div>
          <h3 className="font-medium">{title}</h3>
          <p className="text-sm text-muted-foreground">{text}</p>
        </div>
        {children}
      </div>
    </li>
  )
}

const isBaseline = (r: BulkUploadResponse | BaselineUploadResponse): r is BaselineUploadResponse =>
  'updated' in r

/** Export the catalogue, edit it in Excel, upload it: every change becomes a request to approve (R4). */
export function BulkPanel(props: Props) {
  const { t, toast, accountId, onOpenApprovals } = props
  const queryClient = useQueryClient()
  const isAdmin = useIsAdmin()
  const [file, setFile] = useState<File | null>(null)
  const [mode, setMode] = useState<BulkUploadMode>('update')
  const [result, setResult] = useState<BulkUploadResponse | BaselineUploadResponse | null>(null)

  useEffect(() => {
    setFile(null)
    setResult(null)
  }, [accountId])

  const exportFile = useMutation({
    mutationFn: () => catalogMonitorApi.exportCatalog(accountId),
    onSuccess: (blob) => saveBlob(blob, `catalogo-${today()}.xlsx`),
    onError: (error) =>
      toast({
        title: t('cm.bulk.exportError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const upload = useMutation({
    mutationFn: (args: { file: File; mode: BulkUploadMode }) =>
      catalogMonitorApi.uploadBulk(accountId, args.mode, args.file),
    onSuccess: (res) => {
      setResult(res)
      const keys = isBaseline(res) ? ['baselines', 'anomalies', 'quality'] : ['changes', 'quality']
      for (const key of keys) {
        void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', key] })
      }
    },
    onError: (error) =>
      toast({
        title: t('cm.bulk.uploadError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('cm.bulk.title')}</CardTitle>
        <CardDescription>{t('cm.bulk.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="min-w-[220px] max-w-sm">
          <AccountPicker {...props} />
        </div>

        <ol className="space-y-6">
          <Step n={1} title={t('cm.bulk.step1')} text={t('cm.bulk.step1Text')}>
            <Button
              variant="outline"
              onClick={() => exportFile.mutate()}
              disabled={!accountId || exportFile.isPending}
            >
              {exportFile.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" />
              )}
              {t('cm.bulk.export')}
            </Button>
          </Step>

          <Step n={2} title={t('cm.bulk.step2')} text={t('cm.bulk.step2Text')}>
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[260px] space-y-1">
                <Label>{t('cm.bulk.mode')}</Label>
                <Select value={mode} onValueChange={(v) => setMode(v as BulkUploadMode)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="update">{t('cm.bulk.mode.update')}</SelectItem>
                    <SelectItem value="baseline" disabled={!isAdmin}>
                      {t('cm.bulk.mode.baseline')}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <FilePicker file={file} onChange={setFile} label={t('cm.bulk.chooseFile')} />
              <Button
                onClick={() => file && upload.mutate({ file, mode })}
                disabled={!accountId || !file || upload.isPending}
              >
                {upload.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  mode === 'baseline' && <ShieldCheck className="mr-2 h-4 w-4" />
                )}
                {mode === 'baseline' ? t('cm.bulk.uploadBaseline') : t('cm.bulk.upload')}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {mode === 'baseline' ? t('cm.bulk.mode.baselineHint') : t('cm.bulk.mode.updateHint')}
              {!isAdmin && ` ${t('cm.bulk.mode.baselineAdminOnly')}`}
            </p>
            {upload.isPending && (
              <p className="text-sm text-muted-foreground">{t('cm.bulk.validating')}</p>
            )}
          </Step>

          <Step n={3} title={t('cm.bulk.step3')} text={t('cm.bulk.step3Text')}>
            {result ? (
              isBaseline(result) ? (
                <BaselineResult result={result} t={t} />
              ) : (
                <UploadResult result={result} onOpenApprovals={onOpenApprovals} t={t} />
              )
            ) : (
              <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                {t('cm.bulk.step3Empty')}
              </p>
            )}
          </Step>
        </ol>

        <NewItemsSection {...props} />
      </CardContent>
    </Card>
  )
}
