import { AlertTriangle, Loader2, Radar, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useTranslation } from '@/i18n'

interface ReportStateProps {
  variant: 'empty' | 'loading' | 'generating' | 'failed'
  onGenerate?: () => void
  generateDisabled?: boolean
}

export function ReportState({ variant, onGenerate, generateDisabled }: ReportStateProps) {
  const { t } = useTranslation()

  if (variant === 'loading') {
    return (
      <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('brandIntelligence.state.loading')}
      </div>
    )
  }

  if (variant === 'generating') {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
          <div className="relative">
            <Radar className="h-8 w-8 text-primary" />
            <Loader2 className="absolute inset-0 h-8 w-8 animate-spin text-primary/40" />
          </div>
          <div>
            <p className="text-base font-medium">{t('brandIntelligence.state.generatingTitle')}</p>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {t('brandIntelligence.state.generatingHelp')}
            </p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (variant === 'failed') {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <AlertTriangle className="h-8 w-8 text-destructive" />
          <div>
            <p className="text-base font-medium">{t('brandIntelligence.state.failedTitle')}</p>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">
              {t('brandIntelligence.state.failedHelp')}
            </p>
          </div>
          {onGenerate ? (
            <Button onClick={onGenerate} disabled={generateDisabled}>
              {t('brandIntelligence.action.retry')}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Sparkles className="h-5 w-5" />
        </div>
        <div>
          <p className="text-base font-medium">{t('brandIntelligence.state.emptyTitle')}</p>
          <p className="mt-1 max-w-md text-sm text-muted-foreground">
            {t('brandIntelligence.state.emptyHelp')}
          </p>
        </div>
        {onGenerate ? (
          <Button onClick={onGenerate} disabled={generateDisabled}>
            {t('brandIntelligence.action.generate')}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  )
}
