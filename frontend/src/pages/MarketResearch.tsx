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
import { Checkbox } from '@/components/ui/checkbox'
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
import { cn, formatDate, formatNumber, formatPercent } from '@/lib/utils'
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
  ComparisonMatrixResponse,
  ComparisonDimension,
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

type ComparisonResult = 'better' | 'worse' | 'neutral'

function isLowerBetterDimension(name: ComparisonDimension['name']): boolean {
  return name === 'price' || name === 'bsr'
}

function dimensionLabel(name: ComparisonDimension['name'], t: (key: string) => string): string {
  switch (name) {
    case 'price':
      return t('marketResearch.price')
    case 'bsr':
      return t('marketResearch.bsr')
    case 'reviews':
      return t('marketResearch.reviews')
    case 'rating':
      return t('marketResearch.rating')
  }
}

function formatDimensionValue(
  name: ComparisonDimension['name'],
  value: number | null,
  t: (key: string) => string,
): string {
  if (value == null) return t('marketResearch.noData')

  switch (name) {
    case 'price':
      return `$${value.toFixed(2)}`
    case 'rating':
      return value.toFixed(1)
    case 'bsr':
    case 'reviews':
      return formatNumber(Math.round(value))
  }
}

function getDimensionResult(dimension: ComparisonDimension): ComparisonResult {
  if (dimension.client_value == null || dimension.competitor_avg == null) return 'neutral'
  if (dimension.client_value === dimension.competitor_avg) return 'neutral'

  const clientIsBetter = isLowerBetterDimension(dimension.name)
    ? dimension.client_value < dimension.competitor_avg
    : dimension.client_value > dimension.competitor_avg

  return clientIsBetter ? 'better' : 'worse'
}

function formatDimensionRank(
  dimension: ComparisonDimension,
  t: (key: string) => string,
): string {
  if (dimension.client_rank == null || dimension.total_competitors === 0) {
    return t('marketResearch.noData')
  }
  return `${dimension.client_rank}/${dimension.total_competitors}`
}

function opportunityMessage(
  dimension: ComparisonDimension,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  const gap = Math.abs(dimension.gap_percent ?? 0).toFixed(1)
  const key = isLowerBetterDimension(dimension.name)
    ? 'marketResearch.opportunityAboveAvg'
    : 'marketResearch.opportunityBelowAvg'

  return t(key, {
    dimension: dimensionLabel(dimension.name, t),
    gap,
  })
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
  const [selectedCompetitorAsins, setSelectedCompetitorAsins] = useState<string[]>([])
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

  const comparisonMatrixQuery = useQuery<ComparisonMatrixResponse>({
    queryKey: ['market-research', selectedReportId, 'comparison-matrix'],
    queryFn: () => marketResearchApi.getComparisonMatrix(selectedReportId!),
    enabled:
      !!selectedReportId &&
      selectedReport?.id === selectedReportId &&
      selectedReport?.status === 'completed' &&
      !!selectedReport?.product_snapshot &&
      !!selectedReport?.competitor_data?.length,
  })
  const comparisonMatrix = comparisonMatrixQuery.data

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
  const selectedCompetitors = selectedReport?.competitor_data?.filter((competitor) =>
    selectedCompetitorAsins.includes(competitor.asin)
  ) || []
  const opportunityDimensions = comparisonMatrix?.dimensions.filter((dimension) =>
    comparisonMatrix.opportunities.includes(dimension.name)
  ) || []

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

  useEffect(() => {
    if (!selectedReport?.id) {
      setSelectedCompetitorAsins([])
      return
    }

    const availableAsins = Array.from(
      new Set(
        (selectedReport.competitor_data || [])
          .map((competitor) => competitor.asin)
          .filter((asin): asin is string => Boolean(asin)),
      ),
    )

    setSelectedCompetitorAsins((current) => {
      if (current.length === 0) return availableAsins

      const nextSelection = current.filter((asin) => availableAsins.includes(asin))
      return nextSelection.length > 0 ? nextSelection : availableAsins
    })
  }, [selectedReport?.id, selectedReport?.competitor_data])

  const toggleCompetitorSelection = (asin: string, checked: boolean | 'indeterminate') => {
    setSelectedCompetitorAsins((current) => {
      if (checked === true) {
        return current.includes(asin) ? current : [...current, asin]
      }
      return current.filter((currentAsin) => currentAsin !== asin)
    })
  }

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
                      <CardDescription>{t('marketResearch.radarDesc')}</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="rounded-lg border p-4 space-y-3">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium">
                              {t('marketResearch.selectedCompetitors')}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {t('marketResearch.selectedCompetitorsHint', {
                                selected: selectedCompetitors.length,
                                total: selectedReport.competitor_data.length,
                              })}
                            </p>
                          </div>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setSelectedCompetitorAsins(
                                selectedReport.competitor_data?.map((competitor) => competitor.asin) || [],
                              )
                            }}
                          >
                            {t('marketResearch.selectAllCompetitors')}
                          </Button>
                        </div>
                        <div className="grid gap-2 md:grid-cols-2">
                          {selectedReport.competitor_data.map((competitor) => (
                            <label
                              key={competitor.asin}
                              className={cn(
                                'flex items-start gap-3 rounded-lg border p-3 transition-colors cursor-pointer',
                                selectedCompetitorAsins.includes(competitor.asin)
                                  ? 'border-primary/40 bg-primary/5'
                                  : 'hover:bg-muted/50',
                              )}
                            >
                              <Checkbox
                                checked={selectedCompetitorAsins.includes(competitor.asin)}
                                onCheckedChange={(checked) =>
                                  toggleCompetitorSelection(competitor.asin, checked)
                                }
                                className="mt-0.5"
                              />
                              <div className="min-w-0">
                                <p className="font-mono text-xs">{competitor.asin}</p>
                                <p
                                  className="text-sm text-muted-foreground truncate"
                                  title={competitor.title || competitor.asin}
                                >
                                  {competitor.title || competitor.asin}
                                </p>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>

                      <div ref={radarChartRef}>
                        {selectedCompetitors.length > 0 ? (
                          <RadarComparison
                            product={selectedReport.product_snapshot}
                            competitors={selectedCompetitors}
                          />
                        ) : (
                          <div className="flex min-h-[300px] items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground">
                            {t('marketResearch.noCompetitorsSelected')}
                          </div>
                        )}
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

              {selectedReport.product_snapshot && selectedReport.competitor_data?.length ? (
                comparisonMatrixQuery.isLoading ? (
                  <Card>
                    <CardContent className="py-8 flex items-center gap-3">
                      <Loader2 className="h-5 w-5 animate-spin text-primary shrink-0" />
                      <div>
                        <p className="text-sm font-medium">
                          {t('marketResearch.detailedComparisonTitle')}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {t('marketResearch.comparisonMatrixLoading')}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ) : comparisonMatrix ? (
                  <Card>
                    <CardHeader className="gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <CardTitle>{t('marketResearch.detailedComparisonTitle')}</CardTitle>
                        <CardDescription>{t('marketResearch.detailedComparisonDesc')}</CardDescription>
                      </div>
                      <div className="rounded-lg border px-4 py-3 md:w-[240px]">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-medium text-muted-foreground">
                            {t('marketResearch.overallScore')}
                          </p>
                          <Badge variant="secondary">
                            {comparisonMatrix.overall_score.toFixed(1)}/100
                          </Badge>
                        </div>
                        <Progress value={comparisonMatrix.overall_score} className="mt-3 h-2" />
                        <p className="mt-2 text-xs text-muted-foreground">
                          {t('marketResearch.overallScoreHelper')}
                        </p>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-5">
                      <div className="overflow-x-auto rounded-lg border">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b bg-muted/50">
                              <th className="px-3 py-2 text-left font-medium">
                                {t('marketResearch.dimension')}
                              </th>
                              <th className="px-3 py-2 text-right font-medium">
                                {t('marketResearch.yourProduct')}
                              </th>
                              <th className="px-3 py-2 text-right font-medium">
                                {t('marketResearch.competitorAvg')}
                              </th>
                              <th className="px-3 py-2 text-left font-medium">
                                {t('marketResearch.bestCompetitor')}
                              </th>
                              <th className="px-3 py-2 text-right font-medium">
                                {t('marketResearch.yourRank')}
                              </th>
                              <th className="px-3 py-2 text-right font-medium">
                                {t('marketResearch.gap')}
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {comparisonMatrix.dimensions.map((dimension) => {
                              const dimensionResult = getDimensionResult(dimension)

                              return (
                                <tr
                                  key={dimension.name}
                                  className={cn(
                                    'border-b last:border-0',
                                    dimensionResult === 'better' && 'bg-emerald-50/60',
                                    dimensionResult === 'worse' && 'bg-red-50/60',
                                  )}
                                >
                                  <td className="px-3 py-3 font-medium">
                                    {dimensionLabel(dimension.name, t)}
                                  </td>
                                  <td className="px-3 py-3 text-right font-mono text-xs">
                                    {formatDimensionValue(dimension.name, dimension.client_value, t)}
                                  </td>
                                  <td className="px-3 py-3 text-right font-mono text-xs">
                                    {formatDimensionValue(dimension.name, dimension.competitor_avg, t)}
                                  </td>
                                  <td className="px-3 py-3">
                                    {dimension.competitor_best_name ? (
                                      <div>
                                        <p className="text-sm">{dimension.competitor_best_name}</p>
                                        <p className="text-xs text-muted-foreground font-mono">
                                          {formatDimensionValue(dimension.name, dimension.competitor_best, t)}
                                        </p>
                                      </div>
                                    ) : (
                                      <span className="text-muted-foreground">
                                        {t('marketResearch.noData')}
                                      </span>
                                    )}
                                  </td>
                                  <td className="px-3 py-3 text-right font-mono text-xs">
                                    {formatDimensionRank(dimension, t)}
                                  </td>
                                  <td
                                    className={cn(
                                      'px-3 py-3 text-right font-mono text-xs',
                                      dimensionResult === 'better' && 'text-emerald-700',
                                      dimensionResult === 'worse' && 'text-red-700',
                                    )}
                                  >
                                    {dimension.gap_percent == null
                                      ? t('marketResearch.noData')
                                      : formatPercent(dimension.gap_percent)}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>

                      <div className="space-y-3">
                        <div>
                          <p className="text-sm font-medium">
                            {t('marketResearch.opportunitiesTitle')}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {t('marketResearch.opportunitiesDesc')}
                          </p>
                        </div>

                        {opportunityDimensions.length > 0 ? (
                          <div className="grid gap-3 md:grid-cols-2">
                            {opportunityDimensions.map((dimension) => (
                              <div
                                key={dimension.name}
                                className="rounded-lg border border-red-200 bg-red-50/60 p-4"
                              >
                                <div className="flex items-start gap-3">
                                  <AlertCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                                  <div className="space-y-1">
                                    <p className="text-sm font-medium text-red-900">
                                      {dimensionLabel(dimension.name, t)}
                                    </p>
                                    <p className="text-sm text-red-800">
                                      {opportunityMessage(dimension, t)}
                                    </p>
                                    {dimension.competitor_best_name ? (
                                      <p className="text-xs text-red-700">
                                        {t('marketResearch.bestCompetitorLabel', {
                                          competitor: dimension.competitor_best_name,
                                        })}
                                      </p>
                                    ) : null}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3 text-sm text-emerald-800">
                            {t('marketResearch.noOpportunities')}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ) : comparisonMatrixQuery.isError ? (
                  <Card>
                    <CardContent className="py-6">
                      <p className="text-sm text-muted-foreground">
                        {t('marketResearch.comparisonMatrixFailed')}
                      </p>
                    </CardContent>
                  </Card>
                ) : null
              ) : null}

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
