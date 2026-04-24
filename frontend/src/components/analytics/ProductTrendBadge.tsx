import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/i18n'
import { cn } from '@/lib/utils'
import type { ProductTrendClass } from '@/types'

const trendBadgeStyles: Record<ProductTrendClass, string> = {
  rising_fast: 'border-transparent bg-emerald-600 text-white hover:bg-emerald-600/90',
  rising: 'border-transparent bg-emerald-100 text-emerald-800 hover:bg-emerald-100',
  stable: 'border-transparent bg-slate-100 text-slate-700 hover:bg-slate-100',
  declining: 'border-transparent bg-amber-100 text-amber-900 hover:bg-amber-100',
  declining_fast: 'border-transparent bg-rose-600 text-white hover:bg-rose-600/90',
}

export default function ProductTrendBadge({
  trendClass,
  className,
}: {
  trendClass: ProductTrendClass
  className?: string
}) {
  const { t } = useTranslation()

  return (
    <Badge
      variant="secondary"
      className={cn('capitalize', trendBadgeStyles[trendClass], className)}
    >
      {t(`analytics.trendClass.${trendClass}`)}
    </Badge>
  )
}
