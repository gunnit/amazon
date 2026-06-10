import { useTranslation } from '@/i18n'
import { formatDate } from '@/lib/utils'
import type { BrandIntelligenceReport } from '@/types'
import { ExecSummary } from './ExecSummary'
import { ReportSection } from './ReportSection'
import { SECTION_ORDER } from './sectionMeta'

function orderedSections(report: BrandIntelligenceReport) {
  const rank = new Map(SECTION_ORDER.map((key, i) => [key, i]))
  return [...report.sections].sort(
    (a, b) => (rank.get(a.key) ?? 99) - (rank.get(b.key) ?? 99),
  )
}

export function ReportReader({ report }: { report: BrandIntelligenceReport }) {
  const { t } = useTranslation()
  // Filter empty sections here so the editorial numbering stays contiguous.
  const sections = orderedSections(report).filter(
    (section) => section.narrative || section.items.length > 0,
  )

  return (
    <article className="space-y-10">
      <ExecSummary summary={report.exec_summary} />

      {sections.map((section, index) => (
        <ReportSection key={section.key} section={section} index={index} />
      ))}

      {/* Colophon */}
      <footer className="border-t-2 border-foreground pt-4">
        {report.coverage_note ? (
          <p className="max-w-3xl text-xs leading-5 text-muted-foreground">
            {report.coverage_note}
          </p>
        ) : null}
        <p className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          {report.generated_at ? (
            <span>
              {t('brandIntelligence.footer.generated', { date: formatDate(report.generated_at) })}
            </span>
          ) : null}
          {report.model ? (
            <>
              <span aria-hidden="true">·</span>
              <span>{t('brandIntelligence.footer.model', { model: report.model })}</span>
            </>
          ) : null}
          <span aria-hidden="true" className="text-foreground">
            ■
          </span>
        </p>
      </footer>
    </article>
  )
}
