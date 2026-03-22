import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  Loader2,
  Trash2,
  Eye,
  AlertCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { marketResearchApi, accountsApi, catalogApi } from '@/services/api'
import { formatDate } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import AsinInput from '@/components/market-research/AsinInput'
import CompetitorTable from '@/components/market-research/CompetitorTable'
import RadarComparison from '@/components/market-research/RadarComparison'
import AIInsights from '@/components/market-research/AIInsights'
import type { AmazonAccount, Product, MarketResearchReport, MarketResearchListItem } from '@/types'

const statusVariant: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'outline',
  processing: 'secondary',
  completed: 'default',
  failed: 'destructive',
}

export default function MarketResearch() {
  const [selectedAccount, setSelectedAccount] = useState('')
  const [selectedProductAsin, setSelectedProductAsin] = useState('')
  const [analysisLanguage, setAnalysisLanguage] = useState<'en' | 'it'>('en')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [extraAsins, setExtraAsins] = useState<string[]>([])
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)

  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  // ── Data queries ──

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: products, isLoading: productsLoading } = useQuery<Product[]>({
    queryKey: ['catalog-products', selectedAccount],
    queryFn: () => catalogApi.getProducts({ active_only: true }),
    enabled: !!selectedAccount,
  })

  const { data: reports, isLoading: reportsLoading } = useQuery<MarketResearchListItem[]>({
    queryKey: ['market-research'],
    queryFn: () => marketResearchApi.list(),
  })

  const { data: selectedReport } = useQuery<MarketResearchReport>({
    queryKey: ['market-research', selectedReportId],
    queryFn: () => marketResearchApi.get(selectedReportId!),
    enabled: !!selectedReportId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'pending' || status === 'processing') return 3000
      return false
    },
  })

  // ── Mutations ──

  const generateMutation = useMutation({
    mutationFn: (params: {
      source_asin: string
      account_id: string
      language: string
      extra_competitor_asins?: string[]
    }) => marketResearchApi.generate(params),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['market-research'] })
      setSelectedReportId(data.id)
      toast({ title: t('marketResearch.generateSuccess') })
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('marketResearch.generateFailed') })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => marketResearchApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['market-research'] })
      if (selectedReportId) setSelectedReportId(null)
      toast({ title: t('marketResearch.deleted') })
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('marketResearch.deleteFailed') })
    },
  })

  // ── Handlers ──

  const handleGenerate = () => {
    if (!selectedAccount) {
      toast({ variant: 'destructive', title: t('marketResearch.selectAccountError') })
      return
    }
    if (!selectedProductAsin) return

    generateMutation.mutate({
      source_asin: selectedProductAsin,
      account_id: selectedAccount,
      language: analysisLanguage,
      ...(extraAsins.length > 0 ? { extra_competitor_asins: extraAsins } : {}),
    })
  }

  const handleAccountChange = (accountId: string) => {
    setSelectedAccount(accountId)
    setSelectedProductAsin('')
  }

  const isProcessing =
    selectedReport?.status === 'pending' || selectedReport?.status === 'processing'

  // Get selected product info for display
  const selectedProduct = products?.find((p) => p.asin === selectedProductAsin)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('marketResearch.title')}</h1>
        <p className="text-muted-foreground">{t('marketResearch.subtitle')}</p>
      </div>

      {/* Generate Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            {t('marketResearch.generateTitle')}
          </CardTitle>
          <CardDescription>{t('marketResearch.generateDesc')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-4">
            {/* Account selector */}
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('forecasts.account')}</label>
              <Select value={selectedAccount} onValueChange={handleAccountChange}>
                <SelectTrigger className="w-[220px]">
                  <SelectValue placeholder={t('marketResearch.selectAccount')} />
                </SelectTrigger>
                <SelectContent>
                  {accounts?.map((account) => (
                    <SelectItem key={account.id} value={account.id}>
                      {account.account_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Product selector */}
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('marketResearch.selectProduct')}</label>
              <Select
                value={selectedProductAsin}
                onValueChange={setSelectedProductAsin}
                disabled={!selectedAccount || productsLoading}
              >
                <SelectTrigger className="w-[320px]">
                  {productsLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : null}
                  <SelectValue placeholder={t('marketResearch.selectProduct')} />
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

            {/* Language selector */}
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('marketResearch.analysisLanguage')}</label>
              <Select
                value={analysisLanguage}
                onValueChange={(v) => setAnalysisLanguage(v as 'en' | 'it')}
              >
                <SelectTrigger className="w-[130px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="it">Italiano</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Selected product preview */}
          {selectedProduct && (
            <div className="flex items-center gap-4 px-3 py-2 bg-muted/50 rounded-lg text-sm">
              <span className="font-mono">{selectedProduct.asin}</span>
              {selectedProduct.title && (
                <span className="text-muted-foreground truncate">{selectedProduct.title}</span>
              )}
              {selectedProduct.brand && (
                <Badge variant="outline" className="shrink-0">{selectedProduct.brand}</Badge>
              )}
            </div>
          )}

          {/* Advanced: extra ASINs (optional) */}
          <button
            type="button"
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            {t('marketResearch.addExtraCompetitors')}
          </button>

          {showAdvanced && (
            <div className="space-y-2 pl-5 border-l-2 border-muted">
              <p className="text-xs text-muted-foreground">{t('marketResearch.extraCompetitorsDesc')}</p>
              <AsinInput asins={extraAsins} onChange={setExtraAsins} max={5} />
            </div>
          )}

          <Button
            onClick={handleGenerate}
            disabled={
              generateMutation.isPending || !selectedAccount || !selectedProductAsin
            }
            className="mt-2"
          >
            {generateMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Search className="mr-2 h-4 w-4" />
            )}
            {generateMutation.isPending
              ? t('marketResearch.generating')
              : t('marketResearch.generate')}
          </Button>
        </CardContent>
      </Card>

      {/* Selected Report Display */}
      {selectedReportId && (
        <>
          {isProcessing ? (
            <Card>
              <CardContent className="py-10 flex flex-col items-center gap-3">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <p className="text-sm font-medium">
                  {t(`marketResearch.status.${selectedReport?.status || 'processing'}`)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t('marketResearch.autoDiscovering')}
                </p>
              </CardContent>
            </Card>
          ) : selectedReport?.status === 'failed' ? (
            <Card>
              <CardContent className="py-10 flex flex-col items-center gap-3">
                <AlertCircle className="h-8 w-8 text-destructive" />
                <p className="text-destructive font-medium">
                  {t('marketResearch.status.failed')}
                </p>
                <p className="text-sm text-muted-foreground">
                  {selectedReport.error_message}
                </p>
              </CardContent>
            </Card>
          ) : selectedReport?.status === 'completed' ? (
            <div className="space-y-4">
              {/* Comparison Table */}
              {selectedReport.product_snapshot && selectedReport.competitor_data && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('marketResearch.comparison')}</CardTitle>
                    <CardDescription>
                      {selectedReport.competitor_data.length} {t('marketResearch.competitorsFound')}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <CompetitorTable
                      product={selectedReport.product_snapshot}
                      competitors={selectedReport.competitor_data}
                    />
                  </CardContent>
                </Card>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                {/* Radar Chart */}
                {selectedReport.product_snapshot && selectedReport.competitor_data && (
                  <Card>
                    <CardHeader>
                      <CardTitle>{t('marketResearch.radarTitle')}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <RadarComparison
                        product={selectedReport.product_snapshot}
                        competitors={selectedReport.competitor_data}
                      />
                    </CardContent>
                  </Card>
                )}

                {/* Summary card */}
                {selectedReport.ai_analysis && (
                  <Card>
                    <CardHeader>
                      <CardTitle>{t('marketResearch.summary')}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-muted-foreground">
                        {selectedReport.ai_analysis.summary}
                      </p>
                    </CardContent>
                  </Card>
                )}
              </div>

              {/* AI Insights */}
              {selectedReport.ai_analysis ? (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('marketResearch.aiInsights')}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <AIInsights analysis={selectedReport.ai_analysis} />
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardContent className="py-6 text-center">
                    <p className="text-sm text-muted-foreground">
                      {t('marketResearch.noAiAnalysis')}
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>
          ) : null}
        </>
      )}

      {/* Previous Reports */}
      <Card>
        <CardHeader>
          <CardTitle>{t('marketResearch.previousReports')}</CardTitle>
        </CardHeader>
        <CardContent>
          {reportsLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          ) : !reports || reports.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              {t('marketResearch.noReports')}
            </p>
          ) : (
            <div className="space-y-2">
              {reports.map((report) => (
                <div
                  key={report.id}
                  className={`flex items-center justify-between py-2 px-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedReportId === report.id
                      ? 'bg-primary/5 border-primary/30'
                      : 'hover:bg-muted'
                  }`}
                  onClick={() => setSelectedReportId(report.id)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Badge variant={statusVariant[report.status] || 'outline'}>
                      {t(`marketResearch.status.${report.status}`)}
                    </Badge>
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">
                        {report.title || report.source_asin}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {report.competitor_count} {t('marketResearch.competitors')} · {formatDate(report.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedReportId(report.id)
                      }}
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-destructive"
                      onClick={(e) => {
                        e.stopPropagation()
                        if (confirm(t('marketResearch.deleteConfirm'))) {
                          deleteMutation.mutate(report.id)
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
