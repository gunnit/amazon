import { formatCurrency, formatNumber } from '@/lib/utils'

export interface PricedItem {
  asin: string
  price: number | null
  price_unreliable?: boolean | null
}

export interface MetricBearer {
  price?: number | null
  bsr?: number | null
  review_count?: number | null
  rating?: number | null
}

// Amazon SP-API occasionally returns the same placeholder amount (e.g. a
// barcode/EAN or a marketplace sentinel) on many unrelated listings. A price
// that repeats verbatim across several distinct ASINs is not a real market
// price — including it poisons the average, range and price charts. We detect
// those values and exclude them from any aggregate, while still rejecting
// non-positive prices outright.
const SENTINEL_MIN_OCCURRENCES = 3
const SENTINEL_MIN_SHARE = 0.3
const SENTINEL_MIN_VALUE = 1000

function sentinelPrices(items: PricedItem[]): Set<number> {
  const counts = new Map<number, number>()
  let priced = 0
  for (const item of items) {
    const price = item.price
    if (price == null || price <= 0) continue
    priced += 1
    counts.set(price, (counts.get(price) ?? 0) + 1)
  }

  const sentinels = new Set<number>()
  if (priced < SENTINEL_MIN_OCCURRENCES) return sentinels

  for (const [value, count] of counts) {
    if (
      value >= SENTINEL_MIN_VALUE &&
      count >= SENTINEL_MIN_OCCURRENCES &&
      count / priced >= SENTINEL_MIN_SHARE
    ) {
      sentinels.add(value)
    }
  }
  return sentinels
}

// Prices that survive sanitization: positive, finite and not a detected
// sentinel. Used to drive averages, ranges and the price distribution chart.
export function usablePrices(items: PricedItem[]): number[] {
  const sentinels = sentinelPrices(items)
  return items
    .map((item) => item.price)
    .filter((price, index): price is number => {
      const item = items[index]
      return price != null && price > 0 && Number.isFinite(price) && !item.price_unreliable
    })
    .filter((price) => !sentinels.has(price))
}

// True when a single item's price can be trusted in aggregates/charts.
export function isUsablePrice(price: number | null | undefined, items: PricedItem[]): boolean {
  if (price == null || price <= 0 || !Number.isFinite(price)) return false
  return !sentinelPrices(items).has(price)
}

export function formatEur(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return formatCurrency(value)
}

export function formatEurCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return formatCurrency(Math.round(value))
}

export function formatBsr(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return formatNumber(Math.round(value))
}

// Competitive benchmarking (radar, position summary, "best competitor")
// only makes sense when competitors carry a metric beyond price. BSR,
// reviews and rating come from external data that is currently unavailable,
// so a price-only set must not be dressed up as a full competitive analysis.
export function hasCompetitiveMetrics(items: MetricBearer[]): boolean {
  return items.some(
    (item) =>
      item.bsr != null || item.review_count != null || item.rating != null,
  )
}
