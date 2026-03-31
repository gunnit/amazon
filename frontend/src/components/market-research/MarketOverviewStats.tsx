import { Package, DollarSign, BarChart3, Tag } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { useTranslation } from '@/i18n'
import type { MarketSearchResult } from '@/types'

interface MarketOverviewStatsProps {
  results: MarketSearchResult[]
}

export default function MarketOverviewStats({ results }: MarketOverviewStatsProps) {
  const { t } = useTranslation()

  const prices = results.map((r) => r.price).filter((p): p is number => p != null)
  const bsrs = results.map((r) => r.bsr).filter((b): b is number => b != null)
  const brands = new Set(results.map((r) => r.brand).filter(Boolean))

  const avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : null
  const minPrice = prices.length > 0 ? Math.min(...prices) : null
  const maxPrice = prices.length > 0 ? Math.max(...prices) : null
  const avgBsr = bsrs.length > 0 ? Math.round(bsrs.reduce((a, b) => a + b, 0) / bsrs.length) : null

  const stats = [
    {
      label: t('marketTracker.totalProducts'),
      value: results.length.toString(),
      icon: Package,
      color: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-50 dark:bg-blue-950/30',
    },
    {
      label: t('marketTracker.avgPrice'),
      value: avgPrice != null ? `$${avgPrice.toFixed(2)}` : '--',
      sub: minPrice != null && maxPrice != null ? `$${minPrice.toFixed(0)} - $${maxPrice.toFixed(0)}` : undefined,
      icon: DollarSign,
      color: 'text-emerald-600 dark:text-emerald-400',
      bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    },
    {
      label: t('marketTracker.avgBsr'),
      value: avgBsr != null ? avgBsr.toLocaleString() : '--',
      icon: BarChart3,
      color: 'text-amber-600 dark:text-amber-400',
      bg: 'bg-amber-50 dark:bg-amber-950/30',
    },
    {
      label: t('marketTracker.brands'),
      value: brands.size.toString(),
      icon: Tag,
      color: 'text-violet-600 dark:text-violet-400',
      bg: 'bg-violet-50 dark:bg-violet-950/30',
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {stats.map((stat) => (
        <Card key={stat.label} className="overflow-hidden">
          <CardContent className="p-4">
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <p className="text-xs font-medium text-muted-foreground">{stat.label}</p>
                <p className="text-xl font-bold tracking-tight">{stat.value}</p>
                {stat.sub && (
                  <p className="text-[11px] text-muted-foreground">{stat.sub}</p>
                )}
              </div>
              <div className={`flex items-center justify-center w-9 h-9 rounded-lg ${stat.bg}`}>
                <stat.icon className={`h-4.5 w-4.5 ${stat.color}`} />
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
