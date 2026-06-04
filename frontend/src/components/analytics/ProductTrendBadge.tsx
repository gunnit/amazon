import { ChevronsUp, Minus, TrendingDown, TrendingUp, type LucideIcon } from 'lucide-react'
import { useTranslation } from '@/i18n'
import { cn } from '@/lib/utils'
import type { ProductTrendClass } from '@/types'

const trendChip: Record<ProductTrendClass, { className: string; Icon: LucideIcon }> = {
  rising_fast: {
    className: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
    Icon: ChevronsUp,
  },
  rising: {
    className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    Icon: TrendingUp,
  },
  stable: {
    className: 'bg-slate-500/10 text-slate-600 dark:text-slate-400',
    Icon: Minus,
  },
  declining: {
    className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
    Icon: TrendingDown,
  },
  declining_fast: {
    className: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
    Icon: TrendingDown,
  },
}

export default function ProductTrendBadge({
  trendClass,
  className,
}: {
  trendClass: ProductTrendClass
  className?: string
}) {
  const { t } = useTranslation()
  const { className: chipClassName, Icon } = trendChip[trendClass]
  const label = t(`analytics.trendClass.${trendClass}`)

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        chipClassName,
        className,
      )}
      title={label}
      aria-label={label}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {label}
    </span>
  )
}
