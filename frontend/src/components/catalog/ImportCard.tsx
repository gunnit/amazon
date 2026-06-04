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
import type { ImportResult, ImportRowResult, TabProps } from './types'

export function ImportCard({
  onSuccess,
  ...props
}: TabProps & { onSuccess: () => void }) {
  const { t, toast, accountId } = props
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [lastResult, setLastResult] = useState<ImportResult | null>(null)

  const downloadMutation = useMutation({
    mutationFn: () => catalogApi.downloadImportTemplate(),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'catalog_import_template.csv'
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  const uploadMutation = useMutation({
    mutationFn: () => catalogApi.importProducts({ account_id: accountId, file: file! }),
    onSuccess: (data) => {
      setLastResult(data)
      toast({
        title: t('catalog.import.successTitle'),
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
        title: t('catalog.import.errorTitle'),
        description: String(message),
      })
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('catalog.import.title')}</CardTitle>
        <CardDescription>{t('catalog.import.description')}</CardDescription>
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
            {t('catalog.import.downloadTemplate')}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button variant="outline" onClick={() => fileRef.current?.click()}>
            <Upload className="mr-2 h-4 w-4" />
            {file ? file.name : t('catalog.import.selectFile')}
          </Button>
          <Button
            onClick={() => uploadMutation.mutate()}
            disabled={!file || !accountId || uploadMutation.isPending}
          >
            {uploadMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.import.submit')}
          </Button>
        </div>

        <BulkResultTable<ImportRowResult>
          result={lastResult}
          t={t}
          successLabel={(r) =>
            `${r.asin}${r.title ? ` — ${r.title}` : ''} (${
              r.created ? t('catalog.import.created') : t('catalog.import.updated')
            })`
          }
        />
      </CardContent>
    </Card>
  )
}
