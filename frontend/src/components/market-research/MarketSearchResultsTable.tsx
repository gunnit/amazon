import { useState } from 'react'
import { ArrowUpDown, ArrowUp, ArrowDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/i18n'
import type { MarketSearchResult } from '@/types'

interface MarketSearchResultsTableProps {
  results: MarketSearchResult[]
  referenceAsin: string | null
  onSelectReference: (result: MarketSearchResult) => void
  onProductClick: (result: MarketSearchResult) => void
}

type SortField = 'price' | 'bsr' | 'brand' | 'title'
type SortDir = 'asc' | 'desc'

function formatPrice(val: number | null): string {
  if (val == null) return '--'
  return `$${val.toFixed(2)}`
}

function formatBsr(val: number | null): string {
  if (val == null) return '--'
  return val.toLocaleString()
}

export default function MarketSearchResultsTable({
  results,
  referenceAsin,
  onSelectReference,
  onProductClick,
}: MarketSearchResultsTableProps) {
  const { t } = useTranslation()
  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const prices = results.map((r) => r.price).filter((p): p is number => p != null)
  const bsrs = results.map((r) => r.bsr).filter((b): b is number => b != null)
  const avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : null
  const maxBsr = bsrs.length > 0 ? Math.max(...bsrs) : null

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const sorted = [...results].sort((a, b) => {
    if (!sortField) return 0
    const dir = sortDir === 'asc' ? 1 : -1
    const av = a[sortField]
    const bv = b[sortField]
    if (av == null && bv == null) return 0
    if (av == null) return 1
    if (bv == null) return -1
    if (typeof av === 'string' && typeof bv === 'string') return av.localeCompare(bv) * dir
    return ((av as number) - (bv as number)) * dir
  })

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-40" />
    return sortDir === 'asc' ? (
      <ArrowUp className="h-3 w-3 ml-1" />
    ) : (
      <ArrowDown className="h-3 w-3 ml-1" />
    )
  }

  const getPriceBadge = (price: number | null) => {
    if (price == null || avgPrice == null) return null
    const diff = ((price - avgPrice) / avgPrice) * 100
    if (Math.abs(diff) < 5) return null
    if (diff < 0) {
      return (
        <Badge variant="outline" className="text-[10px] ml-1.5 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800">
          {Math.abs(Math.round(diff))}% {t('marketTracker.priceBelow')}
        </Badge>
      )
    }
    return (
      <Badge variant="outline" className="text-[10px] ml-1.5 text-red-700 dark:text-red-400 border-red-300 dark:border-red-800">
        +{Math.round(diff)}% {t('marketTracker.priceAbove')}
      </Badge>
    )
  }

  const getBsrBar = (bsr: number | null) => {
    if (bsr == null || maxBsr == null || maxBsr === 0) return null
    const pct = Math.min((bsr / maxBsr) * 100, 100)
    const color = pct < 30 ? 'bg-emerald-500' : pct < 60 ? 'bg-amber-500' : 'bg-red-500'
    return (
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs w-16 text-right">{formatBsr(bsr)}</span>
        <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
    )
  }

  return (
    <div className="border rounded-lg overflow-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50">
            <th className="w-10 p-3" />
            <th className="text-left p-3 font-medium">{t('marketResearch.asin')}</th>
            <th
              className="text-left p-3 font-medium cursor-pointer select-none hover:text-primary transition-colors"
              onClick={() => toggleSort('title')}
            >
              <span className="inline-flex items-center">
                {t('marketResearch.title2')}
                <SortIcon field="title" />
              </span>
            </th>
            <th
              className="text-left p-3 font-medium cursor-pointer select-none hover:text-primary transition-colors"
              onClick={() => toggleSort('brand')}
            >
              <span className="inline-flex items-center">
                {t('marketResearch.brand')}
                <SortIcon field="brand" />
              </span>
            </th>
            <th className="text-left p-3 font-medium">{t('marketTracker.category')}</th>
            <th
              className="text-right p-3 font-medium cursor-pointer select-none hover:text-primary transition-colors"
              onClick={() => toggleSort('price')}
            >
              <span className="inline-flex items-center justify-end">
                {t('marketResearch.price')}
                <SortIcon field="price" />
              </span>
            </th>
            <th
              className="text-right p-3 font-medium cursor-pointer select-none hover:text-primary transition-colors"
              onClick={() => toggleSort('bsr')}
            >
              <span className="inline-flex items-center justify-end">
                {t('marketResearch.bsr')}
                <SortIcon field="bsr" />
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((result) => {
            const isRef = result.asin === referenceAsin
            return (
              <tr
                key={result.asin}
                className={`border-b last:border-0 cursor-pointer transition-colors ${
                  isRef
                    ? 'bg-primary/5 hover:bg-primary/10'
                    : 'hover:bg-muted/50'
                }`}
                onClick={() => onProductClick(result)}
              >
                <td className="p-3 text-center">
                  <input
                    type="radio"
                    name="reference"
                    checked={isRef}
                    onChange={() => onSelectReference(result)}
                    onClick={(e) => e.stopPropagation()}
                    className="h-3.5 w-3.5 accent-primary cursor-pointer"
                  />
                </td>
                <td className="p-3">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs">{result.asin}</span>
                    {isRef && (
                      <Badge variant="default" className="text-[10px] px-1.5 py-0">
                        {t('marketTracker.reference')}
                      </Badge>
                    )}
                  </div>
                </td>
                <td className="p-3 max-w-[250px] truncate" title={result.title || ''}>
                  {result.title || '--'}
                </td>
                <td className="p-3">
                  {result.brand ? (
                    <Badge variant="outline" className="text-xs">{result.brand}</Badge>
                  ) : '--'}
                </td>
                <td className="p-3">
                  {result.category ? (
                    <Badge variant="secondary" className="text-[11px] font-normal">{result.category}</Badge>
                  ) : '--'}
                </td>
                <td className="p-3 text-right">
                  <div className="flex items-center justify-end">
                    <span className="font-mono text-xs">{formatPrice(result.price)}</span>
                    {getPriceBadge(result.price)}
                  </div>
                </td>
                <td className="p-3 text-right">
                  {getBsrBar(result.bsr)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
