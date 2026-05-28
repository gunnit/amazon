import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Image as ImageIcon, Loader2, Star, Trash2, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { imagesApi, type ProductImage } from '@/services/api'
import { AccountPicker } from './AccountPicker'
import type { TabProps } from './types'

export function ImagesCard(props: TabProps) {
  const { accountId, toast, t } = props
  const queryClient = useQueryClient()

  const [asin, setAsin] = useState('')
  const [stagedFiles, setStagedFiles] = useState<File[]>([])
  const [mainIndex, setMainIndex] = useState<number>(0)
  const [pushToAmazon, setPushToAmazon] = useState(true)
  const [lastResult, setLastResult] = useState<unknown>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const canQuery = Boolean(accountId && asin)

  const imagesQuery = useQuery({
    queryKey: ['catalog', 'images', accountId, asin],
    queryFn: () => imagesApi.list(asin, accountId),
    enabled: canQuery,
  })

  const uploadMutation = useMutation({
    mutationFn: () =>
      imagesApi.upload({
        asin,
        account_id: accountId,
        files: stagedFiles,
        main_index: stagedFiles.length > 0 ? mainIndex : undefined,
        push_to_amazon: pushToAmazon,
      }),
    onSuccess: (data) => {
      setLastResult(data)
      setStagedFiles([])
      setMainIndex(0)
      if (fileInputRef.current) fileInputRef.current.value = ''
      toast({
        title: t('catalog.images.uploaded'),
        description: data.sp_api_error
          ? t('catalog.images.uploadedS3Only')
          : t('catalog.images.uploadedSuccess'),
      })
      queryClient.invalidateQueries({ queryKey: ['catalog', 'images', accountId, asin] })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (key: string) => imagesApi.remove(asin, accountId, key),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['catalog', 'images', accountId, asin] })
    },
    onError: (err: unknown) => {
      const message = err && typeof err === 'object' && 'response' in err
        ? ((err as { response?: { data?: { detail?: string } } }).response?.data?.detail ?? 'Error')
        : 'Error'
      toast({ variant: 'destructive', title: 'Error', description: String(message) })
    },
  })

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    setStagedFiles(files)
    setMainIndex(0)
  }

  const removeStaged = (idx: number) => {
    setStagedFiles((prev) => prev.filter((_, i) => i !== idx))
    setMainIndex((prev) => (prev === idx ? 0 : prev > idx ? prev - 1 : prev))
  }

  const existing: ProductImage[] = imagesQuery.data?.images ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ImageIcon className="h-5 w-5" />
          {t('catalog.images.title')}
        </CardTitle>
        <CardDescription>{t('catalog.images.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <AccountPicker {...props} />
          <div>
            <Label>{t('catalog.images.asin')}</Label>
            <Input
              placeholder="B0XXXXXXXX"
              value={asin}
              onChange={(e) => setAsin(e.target.value.trim().toUpperCase())}
            />
          </div>
        </div>

        <div className="space-y-2 border rounded-md p-3">
          <Label>{t('catalog.images.selectFiles')}</Label>
          <Input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            onChange={handleFilesSelected}
          />
          {stagedFiles.length > 0 && (
            <div className="grid gap-2 grid-cols-2 md:grid-cols-4">
              {stagedFiles.map((file, idx) => {
                const url = URL.createObjectURL(file)
                const isMain = idx === mainIndex
                return (
                  <div
                    key={`${file.name}-${idx}`}
                    className={`relative rounded border p-2 ${isMain ? 'ring-2 ring-primary' : ''}`}
                  >
                    <img
                      src={url}
                      alt={file.name}
                      className="w-full h-24 object-contain"
                      onLoad={() => URL.revokeObjectURL(url)}
                    />
                    <p className="truncate text-xs mt-1" title={file.name}>
                      {file.name}
                    </p>
                    <div className="flex items-center justify-between mt-1">
                      <Button
                        size="sm"
                        variant={isMain ? 'default' : 'outline'}
                        className="h-7 px-2 text-xs"
                        onClick={() => setMainIndex(idx)}
                      >
                        <Star className="h-3 w-3 mr-1" />
                        {isMain ? t('catalog.images.isMain') : t('catalog.images.setMain')}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0"
                        onClick={() => removeStaged(idx)}
                        aria-label="Remove"
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={pushToAmazon}
                onChange={(e) => setPushToAmazon(e.target.checked)}
              />
              {t('catalog.images.pushToAmazon')}
            </label>
            <Button
              onClick={() => uploadMutation.mutate()}
              disabled={
                !accountId || !asin || stagedFiles.length === 0 || uploadMutation.isPending
              }
            >
              {uploadMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              {t('catalog.images.upload')}
            </Button>
          </div>
        </div>

        <div>
          <p className="text-sm font-medium mb-2">{t('catalog.images.existing')}</p>
          {!canQuery && (
            <p className="text-sm text-muted-foreground">{t('catalog.images.pickAsin')}</p>
          )}
          {canQuery && imagesQuery.isLoading && (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          )}
          {canQuery && !imagesQuery.isLoading && existing.length === 0 && (
            <p className="text-sm text-muted-foreground">{t('catalog.images.empty')}</p>
          )}
          {existing.length > 0 && (
            <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
              {existing.map((img) => (
                <div key={img.key} className="relative rounded border p-2">
                  <img
                    src={img.url}
                    alt={img.filename}
                    className="w-full h-28 object-contain"
                  />
                  <p className="truncate text-xs mt-1" title={img.filename}>
                    {img.filename}
                  </p>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="absolute top-1 right-1 h-7 w-7 p-0"
                    onClick={() => deleteMutation.mutate(img.key)}
                    disabled={deleteMutation.isPending}
                    aria-label="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        {lastResult !== null && (
          <pre className="text-xs bg-muted rounded p-3 overflow-x-auto max-h-64">
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        )}
      </CardContent>
    </Card>
  )
}
