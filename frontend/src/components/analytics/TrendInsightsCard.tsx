import { AlertTriangle, Lightbulb, Sparkles, TrendingDown, TrendingUp } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useTranslation } from '@/i18n'
import type { ProductTrendInsights } from '@/types'

interface TrendInsightsCardProps {
  insights: ProductTrendInsights
  generatedWithAi: boolean
  aiAvailable: boolean
}

const priorityVariants: Record<string, 'destructive' | 'warning' | 'secondary'> = {
  high: 'destructive',
  medium: 'warning',
  low: 'secondary',
}

export default function TrendInsightsCard({
  insights,
  generatedWithAi,
  aiAvailable,
}: TrendInsightsCardProps) {
  const { t } = useTranslation()

  return (
    <Card className="col-span-2">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{t('analytics.trendInsights')}</CardTitle>
            <CardDescription>{t('analytics.trendInsightsDesc')}</CardDescription>
          </div>
          <Badge variant={generatedWithAi ? 'default' : 'outline'}>
            {generatedWithAi
              ? t('analytics.insightsSource.ai')
              : aiAvailable
                ? t('analytics.insightsSource.fallback')
                : t('analytics.insightsSource.data')}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="rounded-lg border bg-muted/30 p-4">
          <div className="mb-2 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <p className="text-sm font-medium">{t('analytics.executiveSummary')}</p>
          </div>
          <p className="text-sm text-muted-foreground">{insights.summary}</p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border p-4">
            <div className="mb-3 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-green-500" />
              <p className="text-sm font-medium">{t('analytics.keyTrends')}</p>
            </div>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {insights.key_trends.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-red-500" />
              <p className="text-sm font-medium">{t('analytics.risks')}</p>
            </div>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {insights.risks.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="rounded-lg border p-4">
            <div className="mb-3 flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-amber-500" />
              <p className="text-sm font-medium">{t('analytics.opportunities')}</p>
            </div>
            <ul className="space-y-2 text-sm text-muted-foreground">
              {insights.opportunities.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <TrendingDown className="h-4 w-4 text-primary" />
            <p className="text-sm font-medium">{t('analytics.recommendations')}</p>
          </div>
          {insights.recommendations.map((recommendation, index) => (
            <div key={`${recommendation.action}-${index}`} className="rounded-lg border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{recommendation.action}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{recommendation.rationale}</p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {recommendation.expected_impact}
                  </p>
                </div>
                <Badge variant={priorityVariants[recommendation.priority] || 'secondary'}>
                  {t(`marketResearch.priority.${recommendation.priority}`)}
                </Badge>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
