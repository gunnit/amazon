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
  const sections = orderedSections(report)

  return (
    <article className="space-y-5">
      <ExecSummary summary={report.exec_summary} />

      {sections.map((section) => (
        <ReportSection key={section.key} section={section} />
      ))}

      <footer className="rounded-lg border bg-muted/30 px-4 py-3 text-xs text-muted-foreground">
        {report.coverage_note ? (
          <p className="leading-6">{report.coverage_note}</p>
        ) : null}
        <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1">
          {report.generated_at ? (
            <span>{t('brandIntelligence.footer.generated', { date: formatDate(report.generated_at) })}</span>
          ) : null}
          {report.model ? (
            <>
              <span aria-hidden>·</span>
              <span>{t('brandIntelligence.footer.model', { model: report.model })}</span>
            </>
          ) : null}
        </p>
      </footer>
    </article>
  )
}
