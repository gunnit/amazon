import { CheckCircle2, XCircle, Lightbulb } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useTranslation } from '@/i18n'
import type { AIAnalysis } from '@/types'

interface AIInsightsProps {
  analysis: AIAnalysis
}

const priorityColors: Record<string, string> = {
  high: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
}

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-600 dark:text-green-400'
  if (score >= 50) return 'text-yellow-600 dark:text-yellow-400'
  return 'text-red-600 dark:text-red-400'
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-green-100 dark:bg-green-900/30'
  if (score >= 50) return 'bg-yellow-100 dark:bg-yellow-900/30'
  return 'bg-red-100 dark:bg-red-900/30'
}

export default function AIInsights({ analysis }: AIInsightsProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-4">
      {/* Overall Score */}
      <div className="flex items-center gap-4">
        <div className={`flex items-center justify-center w-16 h-16 rounded-full ${scoreBg(analysis.overall_score)}`}>
          <span className={`text-2xl font-bold ${scoreColor(analysis.overall_score)}`}>
            {analysis.overall_score}
          </span>
        </div>
        <div>
          <p className="font-semibold">{t('marketResearch.overallScore')}</p>
          <p className="text-sm text-muted-foreground">{analysis.summary}</p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {/* Strengths */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-green-500" />
              {t('marketResearch.strengths')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {analysis.strengths.map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 text-green-500 shrink-0" />
                  {s}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Weaknesses */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <XCircle className="h-4 w-4 text-red-500" />
              {t('marketResearch.weaknesses')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {analysis.weaknesses.map((w, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <XCircle className="h-3.5 w-3.5 mt-0.5 text-red-500 shrink-0" />
                  {w}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      {/* Recommendations */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Lightbulb className="h-4 w-4 text-yellow-500" />
            {t('marketResearch.recommendations')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {analysis.recommendations.map((rec, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded-lg border">
                <Badge
                  className={`shrink-0 text-[10px] ${priorityColors[rec.priority] || ''}`}
                  variant="outline"
                >
                  {t(`marketResearch.priority.${rec.priority}`)}
                </Badge>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{rec.area}</p>
                  <p className="text-sm text-muted-foreground">{rec.action}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {rec.expected_impact}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
