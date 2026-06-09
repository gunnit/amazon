import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { BrandIntelligenceSection } from '@/types'
import { SECTION_META } from './sectionMeta'
import { IntelItem } from './IntelItem'

function SectionDelta({ delta }: { delta: number }) {
  const positive = delta > 0
  const tone = positive
    ? 'text-emerald-600 dark:text-emerald-400'
    : delta < 0
      ? 'text-rose-600 dark:text-rose-400'
      : 'text-muted-foreground'
  const rounded = Math.round(delta * 10) / 10
  return (
    <span className={`flex items-center gap-0.5 text-xs font-medium tabular-nums ${tone}`}>
      {positive ? (
        <ArrowUpRight className="h-3.5 w-3.5" />
      ) : delta < 0 ? (
        <ArrowDownRight className="h-3.5 w-3.5" />
      ) : null}
      {positive ? '+' : ''}
      {rounded}%
    </span>
  )
}

export function ReportSection({ section }: { section: BrandIntelligenceSection }) {
  // Don't render a broken block: skip a section with neither narrative nor items.
  if (!section.narrative && section.items.length === 0) return null

  const meta = SECTION_META[section.key]
  const Icon = meta?.icon

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            {Icon ? <Icon className="h-4 w-4 text-muted-foreground" /> : null}
            {section.title}
          </CardTitle>
          {section.delta != null ? <SectionDelta delta={section.delta} /> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {section.narrative ? (
          <p className="text-sm leading-7 text-foreground/90">{section.narrative}</p>
        ) : null}
        {section.items.length > 0 ? (
          <div className="space-y-2.5">
            {section.items.map((item, i) => (
              <IntelItem key={`${section.key}-${i}`} item={item} />
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
