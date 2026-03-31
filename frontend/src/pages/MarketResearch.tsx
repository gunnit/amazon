import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search,
  Loader2,
  Trash2,
  Eye,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Globe,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import MarketTracker, { type MarketTrackerState } from '@/components/market-research/MarketTracker'
import MarketPositionSummary from '@/components/market-research/MarketPositionSummary'
import MarketOverviewStats from '@/components/market-research/MarketOverviewStats'
import PriceDistributionChart from '@/components/market-research/PriceDistributionChart'
import BsrPositionChart from '@/components/market-research/BsrPositionChart'
import MarketSearchResultsTable from '@/components/market-research/MarketSearchResultsTable'
import ProductDetailDialog from '@/components/market-research/ProductDetailDialog'
import PdfExportButton from '@/components/market-research/PdfExportButton'
import type {
  AmazonAccount,
  MarketSearchResult,
  Product,
  MarketResearchReport,
  MarketResearchListItem,
} from '@/types'

const statusVariant: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'outline',
  processing: 'secondary',
  completed: 'default',
  failed: 'destructive',
}

function isMarketSearchReport(report: Pick<MarketResearchReport, 'title'> | null | undefined): boolean {
  return report?.title?.startsWith('Market Search:') ?? false
}

function reportTypeLabelKey(report: { title?: string | null } | null | undefined): string {
  return isMarketSearchReport(report as Pick<MarketResearchReport, 'title'> | null | undefined)
    ? 'marketResearch.marketTrackerTab'
    : 'marketResearch.productAnalysisTab'
}

export default function MarketResearch() {
  // ── Shared state ──
  const [selectedAccount, setSelectedAccount] = useState('')
  const [analysisLanguage, setAnalysisLanguage] = useState<'en' | 'it'>('en')
  const [activeTab, setActiveTab] = useState<'product-analysis' | 'market-search'>('product-analysis')
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [marketTrackerState, setMarketTrackerState] = useState<MarketTrackerState>({
    searchType: 'keyword',
    searchQuery: '',
    searchResults: null,
    referenceAsin: null,
  })

  // ── Product Analysis state ──
  const [selectedProductAsin, setSelectedProductAsin] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [extraAsins, setExtraAsins] = useState<string[]>([])
  const [historicalMarketProduct, setHistoricalMarketProduct] = useState<MarketSearchResult | null>(null)
  const [historicalMarketDialogOpen, setHistoricalMarketDialogOpen] = useState(false)

  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()
  const reportSectionRef = useRef<HTMLDivElement | null>(null)
  const priceDistChartRef = useRef<HTMLDivElement>(null)
  const bsrChartRef = useRef<HTMLDivElement>(null)
  const radarChartRef = useRef<HTMLDivElement>(null)

  const pdfChartRefs = {
    price_distribution: priceDistChartRef,
    bsr_position: bsrChartRef,
    radar_comparison: radarChartRef,
  }

  // ── Data queries ──

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: products, isLoading: productsLoading } = useQuery<Product[]>({
    queryKey: ['catalog-products', selectedAccount],
    queryFn: () => catalogApi.getProducts({ active_only: true, account_ids: [selectedAccount] }),
    enabled: !!selectedAccount,
  })

  const { data: reports, isLoading: reportsLoading } = useQuery<MarketResearchListItem[]>({
    queryKey: ['market-research'],
    queryFn: () => marketResearchApi.list(),
  })

  const selectedReportQuery = useQuery<MarketResearchReport>({
    queryKey: ['market-research', selectedReportId],
    queryFn: () => marketResearchApi.get(selectedReportId!),
    enabled: !!selectedReportId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'pending' || status === 'processing') return 3000
      return false
    },
  })
  const selectedReport = selectedReportQuery.data

  // ── Mutations ──

  const generateMutation = useMutation({
    mutationFn: (params: {
      source_asin?: string
      account_id: string
      language: string
      extra_competitor_asins?: string[]
      market_competitor_asins?: string[]
      search_query?: string
      search_type?: string
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
    setMarketTrackerState({
      searchType: 'keyword',
      searchQuery: '',
      searchResults: null,
      referenceAsin: null,
    })
  }

  const scrollToReport = () => {
    window.requestAnimationFrame(() => {
      reportSectionRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    })
  }

  const handleSelectReport = (reportId: string, reportTitle?: string | null) => {
    setSelectedReportId(reportId)
    if (reportTitle) {
      setActiveTab(isMarketSearchReport({ title: reportTitle }) ? 'market-search' : 'product-analysis')
    }
    scrollToReport()
  }

  const selectedReportListItem = reports?.find((report) => report.id === selectedReportId)
  const selectedReportMatches = selectedReport?.id === selectedReportId
  const selectedReportStatus = selectedReportMatches
    ? selectedReport?.status
    : selectedReportListItem?.status
  const isProcessing =
    selectedReportStatus === 'pending' || selectedReportStatus === 'processing'
  const reportIsMarketSearch = isMarketSearchReport(selectedReport)

  const selectedProduct = products?.find((p) => p.asin === selectedProductAsin)
  const historicalMarketResults: MarketSearchResult[] = reportIsMarketSearch && selectedReport?.product_snapshot
    ? [
        selectedReport.product_snapshot,
        ...(selectedReport.competitor_data || []),
      ].map((item) => ({
        asin: item.asin,
        title: item.title,
        brand: item.brand,
        category: item.category,
        price: item.price,
        bsr: item.bsr,
        review_count: item.review_count,
        rating: item.rating,
      }))
    : []
  const historicalPrices = historicalMarketResults
    .map((item) => item.price)
    .filter((price): price is number => price != null)
  const historicalBsrs = historicalMarketResults
    .map((item) => item.bsr)
    .filter((bsr): bsr is number => bsr != null)
  const historicalAvgPrice = historicalPrices.length > 0
    ? historicalPrices.reduce((sum, price) => sum + price, 0) / historicalPrices.length
    : null
  const historicalAvgBsr = historicalBsrs.length > 0
    ? historicalBsrs.reduce((sum, bsr) => sum + bsr, 0) / historicalBsrs.length
    : null

  // When a report finishes (completed/failed), refresh the list so the badge updates
  useEffect(() => {
    if (selectedReport?.status === 'completed' || selectedReport?.status === 'failed') {
      queryClient.invalidateQueries({ queryKey: ['market-research'] })
    }
  }, [selectedReport?.status])

  useEffect(() => {
    if (!selectedReportId) return
    scrollToReport()
  }, [selectedReportId])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('marketResearch.title')}</h1>
        <p className="text-muted-foreground">{t('marketResearch.subtitle')}</p>
      </div>

      {/* Account + Language selectors (shared across tabs) */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-4">
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
        </CardContent>
      </Card>

      {/* Tabs: Product Analysis + Market Search */}
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as 'product-analysis' | 'market-search')} className="space-y-4">
        <TabsList>
          <TabsTrigger value="product-analysis" className="gap-2">
            <Search className="h-4 w-4" />
            {t('marketResearch.productAnalysisTab')}
          </TabsTrigger>
          <TabsTrigger value="market-search" className="gap-2">
            <Globe className="h-4 w-4" />
            {t('marketResearch.marketTrackerTab')}
          </TabsTrigger>
        </TabsList>

        {/* ── Tab 1: Product Analysis (existing) ── */}
        <TabsContent value="product-analysis">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Search className="h-5 w-5" />
                {t('marketResearch.generateTitle')}
              </CardTitle>
              <CardDescription>{t('marketResearch.generateDesc')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {t('marketResearch.productAnalysisHelper')}
              </p>

              {/* Product selector */}
              <div className="space-y-2">
                <label className="text-sm font-medium">{t('marketResearch.selectProduct')}</label>
                <Select
                  value={selectedProductAsin}
                  onValueChange={setSelectedProductAsin}
                  disabled={!selectedAccount || productsLoading}
                >
                  <SelectTrigger className="w-[400px]">
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
                              ? product.title.slice(0, 50) + '\u2026'
                              : product.title
                            : product.asin}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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

              {/* Advanced: extra ASINs */}
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
                disabled={generateMutation.isPending || !selectedAccount || !selectedProductAsin}
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
        </TabsContent>

        {/* ── Tab 2: Market Tracker 360 ── */}
        <TabsContent value="market-search">
          <MarketTracker
            selectedAccount={selectedAccount}
            analysisLanguage={analysisLanguage}
            state={marketTrackerState}
            onStateChange={setMarketTrackerState}
            onGenerateReport={(params) => {
              generateMutation.mutate({
                account_id: selectedAccount,
                language: analysisLanguage,
                search_query: params.search_query,
                search_type: params.search_type,
                ...(params.source_asin ? { source_asin: params.source_asin } : {}),
                ...(params.market_competitor_asins
                  ? { market_competitor_asins: params.market_competitor_asins }
                  : {}),
              })
            }}
            isGenerating={generateMutation.isPending}
          />
        </TabsContent>
      </Tabs>

      {/* Selected Report Display */}
      {selectedReportId && (
        <div ref={reportSectionRef}>
          {!selectedReportMatches && selectedReportQuery.isFetching ? (
            <Card>
              <CardContent className="py-8 flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
                <div>
                  <p className="text-sm font-medium">{t('marketResearch.loadingReport')}</p>
                  <p className="text-xs text-muted-foreground">
                    {selectedReportListItem?.title || selectedReportId}
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : isProcessing ? (
            <Card>
              <CardContent className="py-8 space-y-4">
                <div className="flex items-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">
                      {selectedReport?.progress_step || t(`marketResearch.status.${selectedReportStatus || 'processing'}`)}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t(
                        reportIsMarketSearch
                          ? 'marketResearch.marketSearchProgress'
                          : 'marketResearch.productResearchProgress'
                      )}
                    </p>
                  </div>
                  <span className="text-sm font-mono text-muted-foreground tabular-nums shrink-0">
                    {selectedReport?.progress_pct || 0}%
                  </span>
                </div>
                <Progress value={selectedReport?.progress_pct || 0} className="h-2" />
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
              {/* PDF Export Button */}
              <div className="flex justify-end">
                <PdfExportButton report={selectedReport} chartRefs={pdfChartRefs} />
              </div>

              {reportIsMarketSearch && historicalMarketResults.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('marketResearch.marketSnapshotTitle')}</CardTitle>
                    <CardDescription>{t('marketResearch.marketSnapshotDesc')}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <MarketOverviewStats results={historicalMarketResults} />
                    <div className="grid gap-3 md:grid-cols-2">
                      <div ref={priceDistChartRef}>
                        <PriceDistributionChart results={historicalMarketResults} />
                      </div>
                      <div ref={bsrChartRef}>
                        <BsrPositionChart
                          results={historicalMarketResults}
                          referenceAsin={selectedReport.product_snapshot?.asin || null}
                        />
                      </div>
                    </div>
                    <MarketSearchResultsTable
                      results={historicalMarketResults}
                      referenceAsin={selectedReport.product_snapshot?.asin || null}
                      onSelectReference={() => {}}
                      onProductClick={(product) => {
                        setHistoricalMarketProduct(product)
                        setHistoricalMarketDialogOpen(true)
                      }}
                    />
                  </CardContent>
                </Card>
              )}

              {selectedReport.product_snapshot && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('marketResearch.reportContextTitle')}</CardTitle>
                    <CardDescription>
                      {reportIsMarketSearch
                        ? t('marketResearch.marketTrackerHelper')
                        : t('marketResearch.productAnalysisHelper')}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-3 md:grid-cols-2">
                    <div className="rounded-lg border p-4">
                      <p className="text-xs font-medium text-muted-foreground">
                        {t('marketResearch.referenceProduct')}
                      </p>
                      <p className="mt-1 font-mono text-sm">{selectedReport.product_snapshot.asin}</p>
                      <p className="mt-2 text-sm">
                        {selectedReport.product_snapshot.title || selectedReport.title || '—'}
                      </p>
                    </div>
                    <div className="rounded-lg border p-4">
                      <p className="text-xs font-medium text-muted-foreground">
                        {t('marketResearch.marketSample')}
                      </p>
                      <p className="mt-1 text-2xl font-semibold">
                        {selectedReport.competitor_data?.length || 0}
                      </p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {t(
                          reportIsMarketSearch
                            ? 'marketResearch.marketSampleFound'
                            : 'marketResearch.competitorsFound'
                        )}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Comparison Table */}
              {selectedReport.product_snapshot && selectedReport.competitor_data && (
                <Card>
                  <CardHeader>
                    <CardTitle>{t('marketResearch.comparison')}</CardTitle>
                    <CardDescription>
                      {selectedReport.competitor_data.length}{' '}
                      {t(
                        reportIsMarketSearch
                          ? 'marketResearch.marketSampleFound'
                          : 'marketResearch.competitorsFound'
                      )}
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
                      <div ref={radarChartRef}>
                        <RadarComparison
                          product={selectedReport.product_snapshot}
                          competitors={selectedReport.competitor_data}
                        />
                      </div>
                    </CardContent>
                  </Card>
                )}

                {selectedReport.product_snapshot && selectedReport.competitor_data && (
                  <MarketPositionSummary
                    product={selectedReport.product_snapshot}
                    competitors={selectedReport.competitor_data}
                  />
                )}
              </div>

              <div className="grid gap-4 md:grid-cols-2">
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
        </div>
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
                  onClick={() => handleSelectReport(report.id, report.title)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Badge variant={statusVariant[report.status] || 'outline'}>
                      {t(`marketResearch.status.${report.status}`)}
                    </Badge>
                    <Badge variant="secondary">
                      {t(reportTypeLabelKey(report))}
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
                        handleSelectReport(report.id, report.title)
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

      <ProductDetailDialog
        product={historicalMarketProduct}
        open={historicalMarketDialogOpen}
        onClose={() => setHistoricalMarketDialogOpen(false)}
        onSelectAsReference={() => {}}
        averagePrice={historicalAvgPrice}
        averageBsr={historicalAvgBsr}
      />
    </div>
  )
}
