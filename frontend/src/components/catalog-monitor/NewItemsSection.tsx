import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { catalogMonitorApi } from '@/services/api'
import { apiErrorDetail } from '@/lib/apiError'
import type { BulkUploadResponse } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { saveBlob } from './download'
import { FilePicker } from './FilePicker'
import { UploadResult } from './UploadResult'

interface Props extends Pick<TabProps, 'accountId' | 't' | 'toast'> {
  onOpenApprovals: (batchId?: string | null) => void
}

/** New items: a template per product type with its required attributes, then an upload to approve. */
export function NewItemsSection({ accountId, t, toast, onOpenApprovals }: Props) {
  const queryClient = useQueryClient()
  const [productType, setProductType] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<BulkUploadResponse | null>(null)
  const type = productType.trim().toUpperCase()

  useEffect(() => {
    setFile(null)
    setResult(null)
  }, [accountId])

  const template = useMutation({
    mutationFn: (pt: string) => catalogMonitorApi.newItemsTemplate(accountId, pt),
    onSuccess: (blob, pt) => saveBlob(blob, `nuovi-articoli-${pt}.xlsx`),
    onError: (error) =>
      toast({
        title: t('cm.newItems.templateError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  const upload = useMutation({
    mutationFn: (f: File) => catalogMonitorApi.uploadNewItems(accountId, f),
    onSuccess: (res) => {
      setResult(res)
      void queryClient.invalidateQueries({ queryKey: ['catalog-monitor', 'changes'] })
    },
    onError: (error) =>
      toast({
        title: t('cm.newItems.uploadError'),
        description: apiErrorDetail(error, t),
        variant: 'destructive',
      }),
  })

  return (
    <section className="space-y-4 border-t pt-6">
      <div>
        <h3 className="font-medium">{t('cm.newItems.title')}</h3>
        <p className="text-sm text-muted-foreground">{t('cm.newItems.description')}</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-[240px] space-y-1">
          <Label htmlFor="cm-new-items-type">{t('cm.newItems.productType')}</Label>
          <Input
            id="cm-new-items-type"
            value={productType}
            placeholder={t('cm.newItems.productTypePlaceholder')}
            onChange={(e) => setProductType(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && type && accountId && !template.isPending) template.mutate(type)
            }}
          />
        </div>
        <Button
          variant="outline"
          onClick={() => template.mutate(type)}
          disabled={!accountId || !type || template.isPending}
        >
          {template.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          {t('cm.newItems.template')}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <FilePicker file={file} onChange={setFile} label={t('cm.bulk.chooseFile')} />
        <Button
          onClick={() => file && upload.mutate(file)}
          disabled={!accountId || !file || upload.isPending}
        >
          {upload.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t('cm.newItems.upload')}
        </Button>
      </div>
      {upload.isPending && <p className="text-sm text-muted-foreground">{t('cm.bulk.validating')}</p>}
      {result && (
        <UploadResult result={result} newItems onOpenApprovals={onOpenApprovals} t={t} />
      )}
    </section>
  )
}
