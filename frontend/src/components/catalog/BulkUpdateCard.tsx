import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Download, Loader2, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { catalogApi } from '@/services/api'
import { AccountPicker } from './AccountPicker'
import { BulkResultTable } from './BulkResultTable'
import { ConfirmDialog } from './ConfirmDialog'
import type { BulkListingUpdateResult, BulkResult, TabProps } from './types'

export function BulkUpdateCard({
  onSuccess,
  ...props
}: TabProps & { onSuccess: () => void }) {
  const { t, toast, accountId } = props
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [lastResult, setLastResult] = useState<BulkResult<BulkListingUpdateResult> | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const downloadMutation = useMutation({
    mutationFn: () => catalogApi.downloadBulkTemplate(),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'bulk_listings_template.xlsx'
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: () => catalogApi.bulkUpdate({ account_id: accountId, file: file! }),
    onSuccess: (data) => {
      setLastResult(data)
      toast({
        title: t('catalog.bulk.successTitle'),
        description: t('catalog.result.successCount', {
          succeeded: data.succeeded,
          failed: data.failed,
        }),
      })
      onSuccess()
    },
    onError: (err: unknown) => {
      const message =
        err && typeof err === 'object' && 'response' in err
          ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
          : 'Error'
      toast({
        variant: 'destructive',
        title: t('catalog.bulk.errorTitle'),
        description: String(message),
      })
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('catalog.bulk.title')}</CardTitle>
        <CardDescription>{t('catalog.bulk.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AccountPicker {...props} />

        <div className="flex flex-wrap gap-3">
          <Button
            variant="outline"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
          >
            <Download className="mr-2 h-4 w-4" />
            {t('catalog.bulk.downloadTemplate')}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button variant="outline" onClick={() => fileRef.current?.click()}>
            <Upload className="mr-2 h-4 w-4" />
            {file ? file.name : t('catalog.bulk.selectFile')}
          </Button>
          <Button
            onClick={() => setConfirmOpen(true)}
            disabled={!file || !accountId || uploadMutation.isPending}
          >
            {uploadMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.bulk.submit')}
          </Button>
        </div>

        <ConfirmDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title={t('catalog.bulk.confirmTitle')}
          description={t('catalog.bulk.confirmBody', { name: file?.name ?? '' })}
          confirmLabel={t('catalog.bulk.submit')}
          cancelLabel={t('common.cancel')}
          onConfirm={() => {
            setConfirmOpen(false)
            uploadMutation.mutate()
          }}
        />

        <BulkResultTable<BulkListingUpdateResult>
          result={lastResult}
          t={t}
          successLabel={(r) => `${r.sku} (${r.fields.join(', ')})`}
        />
      </CardContent>
    </Card>
  )
}
