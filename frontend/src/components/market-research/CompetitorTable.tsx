import { useTranslation } from '@/i18n'
import { Badge } from '@/components/ui/badge'
import { formatEur, isUsablePrice } from '@/lib/market-research'
import type { ProductSnapshot, CompetitorSnapshot } from '@/types'

interface CompetitorTableProps {
  product: ProductSnapshot
  competitors: CompetitorSnapshot[]
}

function formatValue(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toLocaleString()
}

function formatRating(val: number | null | undefined): string {
  if (val == null) return '—'
  return val.toFixed(1)
}

type CompareResult = 'better' | 'worse' | 'neutral'

function compare(
  productVal: number | null | undefined,
  competitorVal: number | null | undefined,
  lowerIsBetter = false,
): CompareResult {
  if (productVal == null || competitorVal == null) return 'neutral'
  if (productVal === competitorVal) return 'neutral'
  const isBetter = lowerIsBetter
    ? productVal < competitorVal
    : productVal > competitorVal
  return isBetter ? 'better' : 'worse'
}

function cellClass(result: CompareResult): string {
  if (result === 'better') return 'text-green-600 dark:text-green-400 font-medium'
  if (result === 'worse') return 'text-red-600 dark:text-red-400'
  return ''
}

export default function CompetitorTable({ product, competitors }: CompetitorTableProps) {
  const { t } = useTranslation()

  const rows = [
    { label: 'yourProduct', data: product, isSource: true },
    ...competitors.map((c, i) => ({
      label: `${i + 1}`,
      data: c,
      isSource: false,
    })),
  ]

  // Same sentinel guard as the market search table: a price flagged by the
  // backend (or detected client-side across the rows) is not a real market
  // price and must not be rendered or compared as one.
  const pricedRows = rows.map(({ data }) => ({ asin: data.asin, price: data.price ?? null }))
  const usablePriceOf = (data: ProductSnapshot | CompetitorSnapshot): number | null => {
    if (data.price == null || data.price_unreliable) return null
    return isUsablePrice(data.price, pricedRows) ? data.price : null
  }
  const productPrice = usablePriceOf(product)

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b">
            <th className="text-left py-2 px-3 font-medium">{t('marketResearch.asin')}</th>
            <th className="text-left py-2 px-3 font-medium">{t('marketResearch.title2')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('marketResearch.price')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('marketResearch.bsr')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('marketResearch.reviews')}</th>
            <th className="text-right py-2 px-3 font-medium">{t('marketResearch.rating')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ data, isSource }, idx) => (
            <tr
              key={data.asin + idx}
              className={`border-b last:border-0 ${isSource ? 'bg-primary/5' : ''}`}
            >
              <td className="py-2 px-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs">{data.asin}</span>
                  {isSource && (
                    <Badge variant="default" className="text-[10px] px-1.5 py-0">
                      {t('marketResearch.yourProduct')}
                    </Badge>
                  )}
                </div>
              </td>
              <td className="py-2 px-3 max-w-[200px] truncate" title={data.title || ''}>
                {data.title || '—'}
              </td>
              <td className={`py-2 px-3 text-right ${isSource ? '' : cellClass(compare(productPrice, usablePriceOf(data), true))}`}>
                {data.price != null && usablePriceOf(data) == null ? (
                  <span
                    className="text-xs text-muted-foreground"
                    title={t('marketResearch.priceUnreliableHint')}
                  >
                    {t('marketResearch.priceUnreliable')}
                  </span>
                ) : (
                  formatEur(usablePriceOf(data))
                )}
              </td>
              <td className={`py-2 px-3 text-right ${isSource ? '' : cellClass(compare(product.bsr, data.bsr, true))}`}>
                {formatValue(data.bsr)}
              </td>
              <td className={`py-2 px-3 text-right ${isSource ? '' : cellClass(compare(product.review_count, data.review_count))}`}>
                {formatValue(data.review_count)}
              </td>
              <td className={`py-2 px-3 text-right ${isSource ? '' : cellClass(compare(product.rating, data.rating))}`}>
                {formatRating(data.rating)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
