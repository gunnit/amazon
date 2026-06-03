import { CalendarDays, CalendarRange, Layers } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { Granularity } from '@/lib/granularity'

// Discreet, reusable signal that tells the user which cadence the data is on so
// monthly vendor lumps and daily seller activity are not read as the same shape.
export function GranularityBadge({
  granularity,
  className,
}: {
  granularity: Granularity
  className?: string
}) {
  const { t } = useTranslation()

  if (granularity === 'daily' || granularity === 'unknown') {
    return null
  }

  const Icon =
    granularity === 'mixed' ? Layers : granularity === 'monthly' ? CalendarRange : CalendarDays
  const label =
    granularity === 'mixed'
      ? t('granularity.mixed')
      : t('granularity.monthly')

  return (
    <Badge variant="secondary" className={cn('gap-1.5 font-medium', className)}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </Badge>
  )
}
