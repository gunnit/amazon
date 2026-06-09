import { Card, CardContent } from '@/components/ui/card'
import { useTranslation } from '@/i18n'
import type { BrandIntelligenceExecSummary } from '@/types'
import { KpiStat } from './KpiStat'

export function ExecSummary({ summary }: { summary: BrandIntelligenceExecSummary }) {
  const { t } = useTranslation()
  const vsLabel = t('brandIntelligence.vsPrevWeek')

  return (
    <Card>
      <CardContent className="space-y-5 p-5 sm:p-6">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {t('brandIntelligence.execSummary')}
          </p>
          <p className="mt-2 text-lg font-medium leading-8 text-foreground sm:text-xl">
            {summary.headline}
          </p>
        </div>
        {summary.kpis.length > 0 ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {summary.kpis.map((kpi, i) => (
              <KpiStat key={`${kpi.label}-${i}`} kpi={kpi} vsLabel={vsLabel} />
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
