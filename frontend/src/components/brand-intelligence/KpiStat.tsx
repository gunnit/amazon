import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { eyebrow } from '@/lib/editorial'
import type { BrandIntelligenceKpi } from '@/types'

function tone(trend: BrandIntelligenceKpi['trend']): string {
  if (trend === 'up') return 'text-emerald-600 dark:text-emerald-400'
  if (trend === 'down') return 'text-rose-600 dark:text-rose-400'
  return 'text-muted-foreground'
}

function TrendIcon({ trend }: { trend: BrandIntelligenceKpi['trend'] }) {
  if (trend === 'up') return <ArrowUpRight className="h-3.5 w-3.5" />
  if (trend === 'down') return <ArrowDownRight className="h-3.5 w-3.5" />
  return <Minus className="h-3.5 w-3.5" />
}

function formatDelta(percent: number): string {
  const rounded = Math.abs(percent) >= 10 ? Math.round(percent) : Math.round(percent * 10) / 10
  const sign = percent > 0 ? '+' : ''
  return `${sign}${rounded}%`
}

export function KpiStat({ kpi, vsLabel }: { kpi: BrandIntelligenceKpi; vsLabel: string }) {
  return (
    <div className="border-t-2 border-foreground/80 pt-2.5">
      <p className={eyebrow}>{kpi.label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold leading-none tracking-tight tabular-nums">
        {kpi.value}
      </p>
      {kpi.delta_percent != null ? (
        <div className={`mt-2 flex items-center gap-1 font-mono text-xs font-medium ${tone(kpi.trend)}`}>
          <TrendIcon trend={kpi.trend} />
          <span className="tabular-nums">{formatDelta(kpi.delta_percent)}</span>
          <span className="text-muted-foreground">{vsLabel}</span>
        </div>
      ) : (
        <div className="mt-2 h-4" />
      )}
    </div>
  )
}
