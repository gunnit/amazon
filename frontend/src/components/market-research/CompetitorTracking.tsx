import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { Crosshair, Info, LineChart as LineChartIcon, Loader2, Plus, Trash2 } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { competitorsApi } from '@/services/api'
import { CHART_PRIMARY } from '@/lib/chart-theme'
import { formatEur } from '@/lib/market-research'
import { formatDate, formatNumber } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import { apiErrorDetail } from '@/lib/apiError'
import CompetitorTable from './CompetitorTable'
import type {
  CompetitorHistoryResponse,
  Product,
  ProductSnapshot,
  TrackedCompetitor,
} from '@/types'

const ASIN_RE = /^[A-Z0-9]{10}$/

interface CompetitorTrackingProps {
  selectedAccount: string
  products: Product[] | undefined
}

function toSnapshot(competitor: TrackedCompetitor): ProductSnapshot {
  return {
    asin: competitor.asin,
    title: competitor.title,
    brand: competitor.brand,
    category: null,
    price: competitor.current_price,
    bsr: competitor.current_bsr,
    review_count: competitor.review_count,
    rating: competitor.rating,
  }
}

function productToSnapshot(product: Product): ProductSnapshot {
  return {
    asin: product.asin,
    title: product.title,
    brand: product.brand,
    category: product.category,
    price: product.current_price,
    bsr: product.current_bsr,
    review_count: product.review_count,
    rating: product.rating,
  }
}

function HistoryCharts({ history }: { history: CompetitorHistoryResponse }) {
  const { t } = useTranslation()

  const pricePoints = history.points.filter((p) => p.price != null)
  const bsrPoints = history.points.filter((p) => p.bsr != null)

  if (pricePoints.length < 2 && bsrPoints.length < 2) {
    return (
      <p className="text-sm text-muted-foreground py-3">
        {t('competitorTracking.historyEmpty')}
      </p>
    )
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 py-3">
      {pricePoints.length >= 2 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">
            {t('competitorTracking.priceHistory')}
          </p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={pricePoints} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => formatDate(d)} />
              <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} width={48} />
              <Tooltip
                labelFormatter={(d) => formatDate(String(d))}
                formatter={(value: number) => [formatEur(value), t('marketResearch.price')]}
              />
              <Line type="monotone" dataKey="price" stroke={CHART_PRIMARY} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {bsrPoints.length >= 2 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2">
            {t('competitorTracking.bsrHistory')}
          </p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={bsrPoints} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => formatDate(d)} />
              <YAxis tick={{ fontSize: 10 }} reversed domain={['auto', 'auto']} width={48} />
              <Tooltip
                labelFormatter={(d) => formatDate(String(d))}
                formatter={(value: number) => [formatNumber(value), 'BSR']}
              />
              <Line type="monotone" dataKey="bsr" stroke={CHART_PRIMARY} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

export default function CompetitorTracking({ selectedAccount, products }: CompetitorTrackingProps) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [newAsin, setNewAsin] = useState('')
  const [historyCompetitorId, setHistoryCompetitorId] = useState<string | null>(null)
  const [comparisonAsin, setComparisonAsin] = useState('')

  const { data: competitors, isLoading } = useQuery<TrackedCompetitor[]>({
    queryKey: ['competitors'],
    queryFn: () => competitorsApi.list(),
  })

  const historyQuery = useQuery<CompetitorHistoryResponse>({
    queryKey: ['competitors', historyCompetitorId, 'history'],
    queryFn: () => competitorsApi.history(historyCompetitorId!),
    enabled: !!historyCompetitorId,
  })

  const addMutation = useMutation({
    mutationFn: (asin: string) => competitorsApi.add({ asin, account_id: selectedAccount }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitors'] })
      setNewAsin('')
      toast({ title: t('competitorTracking.added') })
    },
    onError: (error: unknown) => {
      const err = error as { response?: { status?: number; data?: { detail?: string } } }
      const isConflict = err?.response?.status === 409
      toast({
        variant: 'destructive',
        title: isConflict
          ? t('competitorTracking.alreadyTracked')
          : t('competitorTracking.addFailed'),
        description: isConflict ? undefined : apiErrorDetail(err, t),
      })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => competitorsApi.remove(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: ['competitors'] })
      if (historyCompetitorId === id) setHistoryCompetitorId(null)
      toast({ title: t('competitorTracking.removed') })
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('competitorTracking.removeFailed') })
    },
  })

  const handleAdd = () => {
    const asin = newAsin.trim().toUpperCase()
    if (!ASIN_RE.test(asin)) {
      toast({ variant: 'destructive', title: t('competitorTracking.invalidAsin') })
      return
    }
    addMutation.mutate(asin)
  }

  const comparisonProduct = products?.find((p) => p.asin === comparisonAsin)
  const hasCompetitors = !!competitors && competitors.length > 0

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Crosshair className="h-5 w-5" />
            {t('competitorTracking.title')}
          </CardTitle>
          <CardDescription>{t('competitorTracking.desc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Add competitor */}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              value={newAsin}
              onChange={(e) => setNewAsin(e.target.value)}
              placeholder={t('competitorTracking.addPlaceholder')}
              className="w-[280px] font-mono"
              disabled={!selectedAccount || addMutation.isPending}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAdd()
              }}
            />
            <Button
              onClick={handleAdd}
              disabled={!selectedAccount || !newAsin.trim() || addMutation.isPending}
            >
              {addMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              {addMutation.isPending
                ? t('competitorTracking.adding')
                : t('competitorTracking.add')}
            </Button>
          </div>
          {!selectedAccount && (
            <p className="text-xs text-muted-foreground">
              {t('competitorTracking.selectAccountFirst')}
            </p>
          )}

          {/* Honest data-source note */}
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>{t('competitorTracking.dataNote')}</AlertDescription>
          </Alert>

          {/* Tracked list */}
          {isLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : !hasCompetitors ? (
            <div className="flex flex-col items-center py-10">
              <Crosshair className="h-10 w-10 text-muted-foreground/40 mb-3" />
              <p className="text-sm font-medium mb-1">{t('competitorTracking.empty')}</p>
              <p className="text-xs text-muted-foreground text-center max-w-sm">
                {t('competitorTracking.emptyDesc')}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-3 py-2 text-left font-medium">{t('marketResearch.asin')}</th>
                    <th className="px-3 py-2 text-left font-medium">{t('marketResearch.title2')}</th>
                    <th className="px-3 py-2 text-right font-medium">{t('marketResearch.price')}</th>
                    <th className="px-3 py-2 text-right font-medium">{t('marketResearch.bsr')}</th>
                    <th className="px-3 py-2 text-right font-medium">{t('marketResearch.reviews')}</th>
                    <th className="px-3 py-2 text-right font-medium">{t('marketResearch.rating')}</th>
                    <th className="px-3 py-2 text-right font-medium">{t('competitorTracking.lastUpdate')}</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {competitors.map((competitor) => (
                    <tr key={competitor.id} className="border-b last:border-0">
                      <td className="px-3 py-2 font-mono text-xs">{competitor.asin}</td>
                      <td className="px-3 py-2 max-w-[240px] truncate" title={competitor.title || ''}>
                        {competitor.title || '—'}
                        {competitor.brand && (
                          <span className="ml-2 text-xs text-muted-foreground">{competitor.brand}</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs">
                        {competitor.current_price != null
                          ? formatEur(competitor.current_price)
                          : t('marketResearch.noData')}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs">
                        {competitor.current_bsr != null
                          ? formatNumber(competitor.current_bsr)
                          : t('marketResearch.noData')}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs">
                        {competitor.review_count != null
                          ? formatNumber(competitor.review_count)
                          : t('marketResearch.noData')}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs">
                        {competitor.rating != null
                          ? competitor.rating.toFixed(1)
                          : t('marketResearch.noData')}
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-muted-foreground">
                        {competitor.last_snapshot_date
                          ? formatDate(competitor.last_snapshot_date)
                          : t('marketResearch.noData')}
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          title={t('competitorTracking.showHistory')}
                          onClick={() =>
                            setHistoryCompetitorId(
                              historyCompetitorId === competitor.id ? null : competitor.id,
                            )
                          }
                        >
                          <LineChartIcon className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive"
                          onClick={() => {
                            if (confirm(t('competitorTracking.removeConfirm'))) {
                              removeMutation.mutate(competitor.id)
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* History for the selected competitor */}
          {historyCompetitorId && (
            <div className="rounded-lg border px-4 py-2">
              <p className="text-sm font-medium pt-2">
                {t('competitorTracking.historyTitle', {
                  asin:
                    competitors?.find((c) => c.id === historyCompetitorId)?.asin || '',
                })}
              </p>
              {historyQuery.isLoading ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                </div>
              ) : historyQuery.data ? (
                <HistoryCharts history={historyQuery.data} />
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Client vs competitor comparison */}
      <Card>
        <CardHeader>
          <CardTitle>{t('competitorTracking.comparisonTitle')}</CardTitle>
          <CardDescription>{t('competitorTracking.comparisonDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">
              {t('competitorTracking.selectYourProduct')}
            </label>
            <Select
              value={comparisonAsin}
              onValueChange={setComparisonAsin}
              disabled={!selectedAccount || !products?.length}
            >
              <SelectTrigger className="w-[400px]">
                <SelectValue placeholder={t('competitorTracking.selectYourProduct')} />
              </SelectTrigger>
              <SelectContent>
                {products?.map((product) => (
                  <SelectItem key={product.asin} value={product.asin}>
                    <span className="font-mono text-xs mr-2">{product.asin}</span>
                    <span className="truncate">
                      {product.title
                        ? product.title.length > 50
                          ? product.title.slice(0, 50) + '…'
                          : product.title
                        : product.asin}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {comparisonProduct && hasCompetitors ? (
            <CompetitorTable
              product={productToSnapshot(comparisonProduct)}
              competitors={competitors.map(toSnapshot)}
            />
          ) : (
            <p className="text-sm text-muted-foreground py-4">
              {t('competitorTracking.comparisonEmpty')}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
