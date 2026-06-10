import { eyebrow } from '@/lib/editorial'
import { useTranslation } from '@/i18n'
import type { BrandIntelligenceExecSummary } from '@/types'
import { KpiStat } from './KpiStat'

export function ExecSummary({ summary }: { summary: BrandIntelligenceExecSummary }) {
  const { t } = useTranslation()
  const vsLabel = t('brandIntelligence.vsPrevWeek')

  return (
    <header>
      <p className={eyebrow}>{t('brandIntelligence.execSummary')}</p>
      <p className="mt-2 max-w-4xl text-base font-semibold leading-7">{summary.headline}</p>
      {summary.kpis.length > 0 ? (
        <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-6 lg:grid-cols-4">
          {summary.kpis.map((kpi, i) => (
            <KpiStat key={`${kpi.label}-${i}`} kpi={kpi} vsLabel={vsLabel} />
          ))}
        </div>
      ) : null}
    </header>
  )
}
