import type { ReactNode } from 'react'
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  BAR_H_FILL,
  BAR_V_FILL,
  CHART_NEUTRAL,
  CHART_POSITIVE,
} from '@/lib/chart-theme'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'

const tooltipStyle = {
  fontSize: 12,
  borderRadius: 8,
  border: '1px solid hsl(var(--border))',
  background: 'hsl(var(--popover))',
  color: 'hsl(var(--popover-foreground))',
} as const

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function eur(value: number): string {
  return `€${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

function eurCompact(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `€${(value / 1_000_000).toFixed(1)}M`
  if (Math.abs(value) >= 1_000) return `€${Math.round(value / 1_000)}k`
  return `€${Math.round(value)}`
}

// Shared chart shell so every card reads the same (title + framed plot area).
function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function EmptyChartCard({ title, note }: { title: string; note: string }) {
  return (
    <ChartCard title={title}>
      <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed text-center text-xs leading-5 text-muted-foreground">
        <span className="max-w-[200px]">{note}</span>
      </div>
    </ChartCard>
  )
}

/* ── Revenue YoY (2024 vs 2025) ──────────────────────────────────────── */

export function RevenueYoYChart({
  revenue2024,
  revenue2025,
}: {
  revenue2024: unknown
  revenue2025: unknown
}) {
  const { t } = useTranslation()
  const title = t('brandAnalysis.chart.revenueYoY')
  const prev = asNumber(revenue2024)
  const curr = asNumber(revenue2025)

  // Need both years with at least one non-zero bar, else the comparison is hollow.
  const points = [
    { label: '2024', value: prev },
    { label: '2025', value: curr },
  ].filter((p): p is { label: string; value: number } => p.value != null)

  if (points.length < 2 || points.every((p) => p.value === 0)) {
    return <EmptyChartCard title={title} note={t('brandAnalysis.chart.empty.revenue')} />
  }

  return (
    <ChartCard title={title}>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={points} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <XAxis dataKey="label" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={48}
            tickFormatter={(v: number) => eurCompact(v)}
          />
          <Tooltip
            cursor={{ fill: 'hsl(var(--muted) / 0.4)' }}
            contentStyle={tooltipStyle}
            formatter={(value: number) => [eur(value), t('brandAnalysis.label.revenue')]}
          />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={72} fill={BAR_V_FILL} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── Active vs inactive ASINs donut ──────────────────────────────────── */

export function AsinStatusDonut({
  activeAsins,
  inactiveAsins,
}: {
  activeAsins: unknown
  inactiveAsins: unknown
}) {
  const { t } = useTranslation()
  const title = t('brandAnalysis.chart.asinStatus')
  const active = asNumber(activeAsins)
  const inactive = asNumber(inactiveAsins)

  const segments = [
    { key: 'active', label: t('brandAnalysis.label.activeAsins'), value: active, color: CHART_POSITIVE },
    { key: 'inactive', label: t('brandAnalysis.label.inactiveAsins'), value: inactive, color: CHART_NEUTRAL },
  ].filter((s): s is { key: string; label: string; value: number; color: string } => s.value != null)

  const total = segments.reduce((sum, s) => sum + s.value, 0)

  // A donut needs both slices present and a non-zero total to mean anything.
  if (segments.length < 2 || total === 0) {
    return <EmptyChartCard title={title} note={t('brandAnalysis.chart.empty.asinStatus')} />
  }

  return (
    <ChartCard title={title}>
      <div className="flex items-center gap-4">
        <ResponsiveContainer width="55%" height={200}>
          <PieChart>
            <Pie
              data={segments}
              dataKey="value"
              nameKey="label"
              innerRadius={52}
              outerRadius={78}
              paddingAngle={2}
              stroke="none"
            >
              {segments.map((segment) => (
                <Cell key={segment.key} fill={segment.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(value: number, name: string) => [value.toLocaleString(), name]}
            />
          </PieChart>
        </ResponsiveContainer>
        <ul className="flex-1 space-y-2.5">
          {segments.map((segment) => (
            <li key={segment.key} className="flex items-center gap-2.5">
              <span
                aria-hidden="true"
                className="h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ backgroundColor: segment.color }}
              />
              <span className="flex-1 text-xs text-muted-foreground">{segment.label}</span>
              <span className="font-mono text-sm font-semibold tabular-nums">
                {segment.value.toLocaleString()}
              </span>
            </li>
          ))}
          <li className="flex items-center gap-2.5 border-t pt-2.5">
            <span className="flex-1 text-xs font-medium">{t('brandAnalysis.chart.total')}</span>
            <span className="font-mono text-sm font-semibold tabular-nums">
              {total.toLocaleString()}
            </span>
          </li>
        </ul>
      </div>
    </ChartCard>
  )
}

/* ── Top ASINs by 2025 revenue (horizontal bar) ──────────────────────── */

interface TopAsin {
  asin?: string
  product_name?: string | null
  revenue_2025?: number | null
}

export function TopAsinsChart({ topAsins }: { topAsins: unknown }) {
  const { t } = useTranslation()
  const title = t('brandAnalysis.chart.topAsins')

  const data = (Array.isArray(topAsins) ? (topAsins as TopAsin[]) : [])
    .map((item) => ({
      asin: item.asin || '',
      name: item.product_name || item.asin || '',
      revenue: asNumber(item.revenue_2025),
    }))
    .filter((item): item is { asin: string; name: string; revenue: number } =>
      item.revenue != null && item.revenue > 0 && !!item.asin,
    )
    .slice(0, 5)

  if (data.length < 2) {
    return <EmptyChartCard title={title} note={t('brandAnalysis.chart.empty.topAsins')} />
  }

  // Truncate long product names so the Y axis stays legible.
  const labelled = data.map((item) => ({
    ...item,
    label: item.name.length > 28 ? `${item.name.slice(0, 28)}…` : item.name,
  }))

  return (
    <ChartCard title={title}>
      <ResponsiveContainer width="100%" height={Math.max(200, labelled.length * 44)}>
        <BarChart
          data={labelled}
          layout="vertical"
          margin={{ top: 4, right: 16, left: 4, bottom: 4 }}
        >
          <XAxis
            type="number"
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => eurCompact(v)}
          />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={180}
          />
          <Tooltip
            cursor={{ fill: 'hsl(var(--muted) / 0.4)' }}
            contentStyle={tooltipStyle}
            formatter={(value: number, _name, entry) => [
              eur(value),
              (entry?.payload as { asin?: string })?.asin || t('brandAnalysis.label.revenue2025'),
            ]}
          />
          <Bar dataKey="revenue" radius={[0, 4, 4, 0]} maxBarSize={26} fill={BAR_H_FILL} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  )
}

/* ── Grid that lays the three charts out, only rendering the ones with data ─ */

export function BrandOverviewCharts({
  metrics,
  className,
}: {
  metrics: Record<string, unknown>
  className?: string
}) {
  return (
    <div className={cn('grid gap-3 lg:grid-cols-2', className)}>
      <RevenueYoYChart
        revenue2024={metrics.total_revenue_2024}
        revenue2025={metrics.total_revenue_2025}
      />
      <AsinStatusDonut
        activeAsins={metrics.active_asins_2025}
        inactiveAsins={metrics.inactive_asins_2025}
      />
      <div className="lg:col-span-2">
        <TopAsinsChart topAsins={metrics.top_5_asins} />
      </div>
    </div>
  )
}
