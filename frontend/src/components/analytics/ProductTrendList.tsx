import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { ProductTrendItem, TrendDirection } from '@/types'

interface ProductTrendListProps {
  title: string
  description: string
  direction: Extract<TrendDirection, 'up' | 'down'>
  products: ProductTrendItem[]
}

function directionStyles(direction: TrendDirection) {
  if (direction === 'up') {
    return {
      icon: ArrowUpRight,
      scoreClass: 'text-green-600 dark:text-green-400',
      badgeVariant: 'success' as const,
      progressClass: 'bg-green-500',
    }
  }
  if (direction === 'down') {
    return {
      icon: ArrowDownRight,
      scoreClass: 'text-red-600 dark:text-red-400',
      badgeVariant: 'destructive' as const,
      progressClass: 'bg-red-500',
    }
  }
  return {
    icon: ArrowRight,
    scoreClass: 'text-muted-foreground',
    badgeVariant: 'secondary' as const,
    progressClass: 'bg-primary',
  }
}

function strengthValue(score: number) {
  return Math.min(100, Math.max(8, Math.abs(score)))
}

export default function ProductTrendList({
  title,
  description,
  direction,
  products,
}: ProductTrendListProps) {
  const { t } = useTranslation()
  const styles = directionStyles(direction)

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {products.length > 0 ? (
          <div className="space-y-4">
            {products.map((product) => {
              const Icon = styles.icon
              return (
                <div key={product.asin} className="space-y-2 rounded-lg border p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Icon className={`h-4 w-4 shrink-0 ${styles.scoreClass}`} />
                        <p className="truncate text-sm font-semibold">
                          {product.title || product.asin}
                        </p>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {product.asin}
                        {product.category ? ` · ${product.category}` : ''}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className={`text-lg font-semibold ${styles.scoreClass}`}>
                        {product.trend_score > 0 ? '+' : ''}{product.trend_score.toFixed(1)}
                      </p>
                      <Badge variant={styles.badgeVariant}>
                        {t(`analytics.trendStrength.${product.strength}`)}
                      </Badge>
                    </div>
                  </div>

                  <Progress
                    value={strengthValue(product.trend_score)}
                    className="h-2"
                    indicatorClassName={styles.progressClass}
                  />

                  <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
                    <div>
                      <span className="block">{t('analytics.metricRevenue')}</span>
                      <span className="font-medium text-foreground">
                        {formatPercent(product.revenue_change_percent)}
                      </span>
                    </div>
                    <div>
                      <span className="block">{t('analytics.metricUnits')}</span>
                      <span className="font-medium text-foreground">
                        {formatPercent(product.units_change_percent)}
                      </span>
                    </div>
                    <div>
                      <span className="block">{t('analytics.metricCurrentRevenue')}</span>
                      <span className="font-medium text-foreground">
                        {formatCurrency(product.current_revenue)}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Badge variant="outline">
                      {t(`analytics.dataQuality.${product.data_quality}`)}
                    </Badge>
                    {product.reason_tags.slice(0, 3).map((tag) => (
                      <Badge key={tag} variant="secondary">
                        {t(`analytics.reasonTag.${tag}`)}
                      </Badge>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div className="flex min-h-[240px] items-center justify-center text-sm text-muted-foreground">
            {t(
              direction === 'up'
                ? 'analytics.noRisingProducts'
                : 'analytics.noDecliningProducts'
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
