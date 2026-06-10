import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { eyebrow, inkButton } from '@/lib/editorial'
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
      <div className="flex items-center gap-2 py-12 font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t('brandIntelligence.state.loading')}
      </div>
    )
  }

  if (variant === 'generating') {
    return (
      <div className="flex flex-col items-center gap-4 rounded-sm border border-dashed border-foreground/25 px-6 py-16 text-center">
        <Loader2 className="h-6 w-6 animate-spin text-foreground" />
        <div>
          <p className={eyebrow}>{t('brandIntelligence.state.generatingTitle')}</p>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
            {t('brandIntelligence.state.generatingHelp')}
          </p>
        </div>
      </div>
    )
  }

  if (variant === 'failed') {
    return (
      <div className="flex flex-col items-center gap-4 rounded-sm border border-dashed border-rose-500/40 px-6 py-14 text-center">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-700 dark:text-rose-400">
            {t('brandIntelligence.state.failedTitle')}
          </p>
          <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">
            {t('brandIntelligence.state.failedHelp')}
          </p>
        </div>
        {onGenerate ? (
          <Button onClick={onGenerate} disabled={generateDisabled} className={inkButton}>
            {t('brandIntelligence.action.retry')}
          </Button>
        ) : null}
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-4 rounded-sm border border-dashed border-foreground/25 px-6 py-16 text-center">
      <div>
        <p className={eyebrow}>{t('brandIntelligence.state.emptyTitle')}</p>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
          {t('brandIntelligence.state.emptyHelp')}
        </p>
      </div>
      {onGenerate ? (
        <Button onClick={onGenerate} disabled={generateDisabled} className={inkButton}>
          {t('brandIntelligence.action.generate')}
        </Button>
      ) : null}
    </div>
  )
}
