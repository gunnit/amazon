import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/i18n'
import type { BrandIntelligenceConfidence, BrandIntelligenceItem } from '@/types'

const CONFIDENCE_VARIANT: Record<BrandIntelligenceConfidence, 'default' | 'secondary' | 'outline'> = {
  high: 'default',
  medium: 'secondary',
  low: 'outline',
}

// One finding inside a section: claim + supporting detail, with the
// Source / Confidence / Evidence provenance badges that distinguish an
// AI intelligence report from an opaque "magic insight".
export function IntelItem({ item }: { item: BrandIntelligenceItem }) {
  const { t } = useTranslation()
  const hasMeta = item.source || item.confidence || item.evidence

  return (
    <div className="rounded-lg border p-3">
      <p className="text-sm font-medium">{item.title}</p>
      {item.detail ? (
        <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.detail}</p>
      ) : null}
      {hasMeta ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {item.source ? (
            <Badge variant="outline" className="text-[11px] font-normal">
              {t('brandIntelligence.meta.source')}: {item.source}
            </Badge>
          ) : null}
          {item.confidence ? (
            <Badge
              variant={CONFIDENCE_VARIANT[item.confidence]}
              className="text-[11px] capitalize"
            >
              {t('brandIntelligence.meta.confidence')}: {t(`brandIntelligence.confidence.${item.confidence}`)}
            </Badge>
          ) : null}
          {item.evidence ? (
            <Badge variant="outline" className="text-[11px] font-normal text-muted-foreground">
              {t('brandIntelligence.meta.evidence')}: {item.evidence}
            </Badge>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
