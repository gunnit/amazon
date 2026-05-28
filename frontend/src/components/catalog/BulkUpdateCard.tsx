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
import type { TabProps } from './types'

export function BulkUpdateCard({
  onSuccess,
  ...props
}: TabProps & { onSuccess: () => void }) {
  const { t, toast, accountId } = props
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [lastResult, setLastResult] = useState<Record<string, unknown> | null>(null)

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
      toast({ title: t('catalog.bulk.successTitle'), description: t('catalog.bulk.successDesc') })
      onSuccess()
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
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
            onClick={() => uploadMutation.mutate()}
            disabled={!file || !accountId || uploadMutation.isPending}
          >
            {uploadMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('catalog.bulk.submit')}
          </Button>
        </div>

        {lastResult && (
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto max-h-64">
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}
