import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Search, Loader2, Globe } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { marketResearchApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import MarketSearchEmptyState from './MarketSearchEmptyState'
import MarketOverviewStats from './MarketOverviewStats'
import MarketSearchResultsTable from './MarketSearchResultsTable'
import PriceDistributionChart from './PriceDistributionChart'
import BsrPositionChart from './BsrPositionChart'
import ProductDetailDialog from './ProductDetailDialog'
import type { MarketSearchResult, MarketSearchResponse } from '@/types'

export interface MarketTrackerState {
  searchType: 'keyword' | 'brand' | 'asin'
  searchQuery: string
  searchResults: MarketSearchResult[] | null
  referenceAsin: string | null
}

interface MarketTrackerProps {
  selectedAccount: string
  analysisLanguage: 'en' | 'it'
  state: MarketTrackerState
  onStateChange: (state: MarketTrackerState) => void
  onGenerateReport: (params: {
    search_query: string
    search_type: string
    source_asin?: string
    market_competitor_asins?: string[]
  }) => void
  isGenerating: boolean
}

export default function MarketTracker({
  selectedAccount,
  analysisLanguage,
  state,
  onStateChange,
  onGenerateReport,
  isGenerating,
}: MarketTrackerProps) {
  const { t } = useTranslation()
  const { toast } = useToast()

  const [detailProduct, setDetailProduct] = useState<MarketSearchResult | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const { searchType, searchQuery, searchResults, referenceAsin } = state

  const patchState = (patch: Partial<MarketTrackerState>) => {
    onStateChange({
      ...state,
      ...patch,
    })
  }

  const searchMutation = useMutation({
    mutationFn: (params: {
      account_id: string
      search_type: string
      query: string
      language?: string
    }) => marketResearchApi.marketSearch(params),
    onSuccess: (data: MarketSearchResponse) => {
      if (data.results.length > 0) {
        onStateChange({
          ...state,
          searchResults: data.results,
          referenceAsin: data.results[0].asin,
        })
      } else {
        onStateChange({
          ...state,
          searchResults: data.results,
          referenceAsin: null,
        })
        toast({
          variant: 'destructive',
          title: t('marketTracker.noResults'),
          description: t('marketTracker.noResultsDesc'),
        })
      }
    },
    onError: (error: unknown) => {
      console.error('Market search error:', error)
      // Extract detail from various possible error shapes
      const err = error as { response?: { data?: { detail?: string } | string; status?: number }; message?: string }
      let detail: string | undefined
      if (err?.response?.data) {
        if (typeof err.response.data === 'string') {
          detail = err.response.data
        } else {
          detail = err.response.data.detail
        }
      }
      if (!detail && err?.message) {
        detail = err.message
      }
      toast({
        variant: 'destructive',
        title: t('marketTracker.searchFailed'),
        description: detail || t('marketTracker.searchFailedDesc'),
      })
    },
  })

  const handleSearch = () => {
    if (!selectedAccount) {
      toast({ variant: 'destructive', title: t('marketResearch.selectAccountError') })
      return
    }
    if (!searchQuery.trim()) return

    patchState({
      searchResults: null,
      referenceAsin: null,
    })

    searchMutation.mutate({
      account_id: selectedAccount,
      search_type: searchType,
      query: searchQuery.trim(),
      language: analysisLanguage,
    })
  }

  const handleGenerateFromSearch = () => {
    if (!searchQuery.trim()) return
    const competitorAsins = (searchResults || [])
      .filter((product) => product.asin !== referenceAsin)
      .map((product) => product.asin)
      .slice(0, 10)

    onGenerateReport({
      search_query: searchQuery.trim(),
      search_type: searchType,
      ...(referenceAsin ? { source_asin: referenceAsin } : {}),
      ...(competitorAsins.length > 0 ? { market_competitor_asins: competitorAsins } : {}),
    })
  }

  const handleProductClick = (product: MarketSearchResult) => {
    setDetailProduct(product)
    setDetailOpen(true)
  }

  const handleSelectReference = (product: MarketSearchResult) => {
    patchState({ referenceAsin: product.asin })
  }

  // Compute averages for the detail dialog
  const prices = searchResults?.map((r) => r.price).filter((p): p is number => p != null) || []
  const bsrs = searchResults?.map((r) => r.bsr).filter((b): b is number => b != null) || []
  const avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : null
  const avgBsr = bsrs.length > 0 ? bsrs.reduce((a, b) => a + b, 0) / bsrs.length : null

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="h-5 w-5" />
            Market Tracker 360
          </CardTitle>
          <CardDescription>
            {t('marketTracker.emptyDesc')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Search Bar */}
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium">{t('marketTracker.searchType')}</label>
              <Select
                value={searchType}
                onValueChange={(v) => patchState({ searchType: v as 'keyword' | 'brand' | 'asin' })}
              >
                <SelectTrigger className="w-[150px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="keyword">{t('marketTracker.keyword')}</SelectItem>
                  <SelectItem value="brand">{t('marketTracker.brand')}</SelectItem>
                  <SelectItem value="asin">ASIN</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5 flex-1 min-w-[250px]">
              <label className="text-sm font-medium">
                {searchType === 'keyword'
                  ? t('marketTracker.enterKeyword')
                  : searchType === 'brand'
                    ? t('marketTracker.enterBrand')
                    : t('marketTracker.enterAsin')}
              </label>
              <Input
                value={searchQuery}
                onChange={(e) => patchState({ searchQuery: e.target.value })}
                placeholder={
                  searchType === 'keyword'
                    ? 'e.g. wireless earbuds'
                    : searchType === 'brand'
                      ? 'e.g. Sony'
                      : 'e.g. B0GPDSF6CN'
                }
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSearch()
                }}
              />
            </div>

            <Button
              onClick={handleSearch}
              disabled={searchMutation.isPending || !selectedAccount || !searchQuery.trim()}
              className="shrink-0"
            >
              {searchMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Search className="mr-2 h-4 w-4" />
              )}
              {searchMutation.isPending ? t('marketTracker.searching') : t('marketTracker.searchMarket')}
            </Button>
          </div>

          {/* Loading skeleton */}
          {searchMutation.isPending && (
            <div className="space-y-4 animate-pulse">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-24 rounded-lg bg-muted" />
                ))}
              </div>
              <div className="grid md:grid-cols-2 gap-3">
                <div className="h-56 rounded-lg bg-muted" />
                <div className="h-56 rounded-lg bg-muted" />
              </div>
              <div className="h-40 rounded-lg bg-muted" />
            </div>
          )}

          {/* Empty state */}
          {!searchMutation.isPending && searchResults === null && (
            <MarketSearchEmptyState />
          )}

          {/* No results */}
          {!searchMutation.isPending && searchResults !== null && searchResults.length === 0 && (
            <div className="flex flex-col items-center py-12">
              <Search className="h-10 w-10 text-muted-foreground/40 mb-3" />
              <p className="text-sm font-medium mb-1">{t('marketTracker.noResults')}</p>
              <p className="text-xs text-muted-foreground text-center max-w-sm">
                {t('marketTracker.noResultsDesc')}
              </p>
            </div>
          )}

          {/* Results */}
          {!searchMutation.isPending && searchResults && searchResults.length > 0 && (
            <div className="space-y-4">
              {/* Header + Generate button */}
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold">
                    {searchResults.length} {t('marketTracker.totalProducts').toLowerCase()}
                  </h3>
                  <Badge variant="outline" className="text-xs">
                    {searchType}: {searchQuery}
                  </Badge>
                </div>
                <Button
                  onClick={handleGenerateFromSearch}
                  disabled={isGenerating}
                  size="sm"
                >
                  {isGenerating ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Globe className="mr-2 h-4 w-4" />
                  )}
                  {isGenerating ? t('marketTracker.generating') : t('marketTracker.generateFromReference')}
                </Button>
              </div>

              {/* Overview stats */}
              <MarketOverviewStats results={searchResults} />

              {referenceAsin && (
                <div className="rounded-lg border bg-primary/5 p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="text-sm font-semibold">{t('marketTracker.referenceTitle')}</p>
                      <p className="text-sm text-muted-foreground">
                        {t('marketTracker.referenceDesc')}
                      </p>
                    </div>
                    <Badge variant="default">{referenceAsin}</Badge>
                  </div>
                  <p className="mt-3 text-xs text-muted-foreground">
                    {t('marketTracker.referenceHelp')}
                  </p>
                </div>
              )}

              {/* Charts */}
              <div className="grid md:grid-cols-2 gap-3">
                <PriceDistributionChart results={searchResults} />
                <BsrPositionChart results={searchResults} referenceAsin={referenceAsin} />
              </div>

              {/* Results table */}
              <MarketSearchResultsTable
                results={searchResults}
                referenceAsin={referenceAsin}
                onSelectReference={handleSelectReference}
                onProductClick={handleProductClick}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Product detail dialog */}
      <ProductDetailDialog
        product={detailProduct}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        onSelectAsReference={handleSelectReference}
        averagePrice={avgPrice}
        averageBsr={avgBsr}
      />
    </>
  )
}
