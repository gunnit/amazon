import { cn } from '@/lib/utils'
import { monoTag } from '@/lib/editorial'
import { useTranslation } from '@/i18n'
import type { BrandIntelligenceConfidence, BrandIntelligenceItem } from '@/types'

const CONFIDENCE_TONE: Record<BrandIntelligenceConfidence, string> = {
  high: 'border-emerald-500/40 text-emerald-700 dark:text-emerald-400',
  medium: 'border-amber-500/40 text-amber-700 dark:text-amber-400',
  low: '',
}

// One finding inside a section: claim + supporting detail, with the
// Source / Confidence / Evidence provenance tags that distinguish an
// AI intelligence report from an opaque "magic insight".
export function IntelItem({ item }: { item: BrandIntelligenceItem }) {
  const { t } = useTranslation()
  const hasMeta = item.source || item.confidence || item.evidence

  return (
    <div className="border-l-2 border-foreground/20 pl-4">
      <p className="text-sm font-semibold">{item.title}</p>
      {item.detail ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.detail}</p>
      ) : null}
      {hasMeta ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          {item.source ? (
            <span className={monoTag}>
              {t('brandIntelligence.meta.source')}: {item.source}
            </span>
          ) : null}
          {item.confidence ? (
            <span className={cn(monoTag, CONFIDENCE_TONE[item.confidence])}>
              {t('brandIntelligence.meta.confidence')}:{' '}
              {t(`brandIntelligence.confidence.${item.confidence}`)}
            </span>
          ) : null}
          {item.evidence ? (
            <span className={monoTag}>
              {t('brandIntelligence.meta.evidence')}: {item.evidence}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
