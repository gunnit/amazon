import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import type { BrandIntelligenceSection } from '@/types'
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
    <span className={`flex items-center gap-0.5 font-mono text-xs font-medium tabular-nums ${tone}`}>
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

export function ReportSection({
  section,
  index,
}: {
  section: BrandIntelligenceSection
  index?: number
}) {
  // Don't render a broken block: skip a section with neither narrative nor items.
  if (!section.narrative && section.items.length === 0) return null

  return (
    <section className="border-t border-foreground/15 pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="flex items-baseline gap-3">
          {index != null ? (
            <span
              aria-hidden="true"
              className="font-mono text-xs leading-none text-foreground/35"
            >
              {String(index + 1).padStart(2, '0')}
            </span>
          ) : null}
          <span className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-foreground">
            {section.title}
          </span>
        </h3>
        {section.delta != null ? <SectionDelta delta={section.delta} /> : null}
      </div>
      {section.narrative ? (
        <p className="mt-3 max-w-3xl text-sm leading-6 text-foreground/90">{section.narrative}</p>
      ) : null}
      {section.items.length > 0 ? (
        <div className="mt-5 space-y-5">
          {section.items.map((item, i) => (
            <IntelItem key={`${section.key}-${i}`} item={item} />
          ))}
        </div>
      ) : null}
    </section>
  )
}
