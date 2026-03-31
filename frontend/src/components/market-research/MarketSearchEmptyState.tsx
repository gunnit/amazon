import { Search, Globe, TrendingUp } from 'lucide-react'
import { useTranslation } from '@/i18n'

export default function MarketSearchEmptyState() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      <div className="relative mb-6">
        <div className="flex items-center justify-center w-20 h-20 rounded-full bg-primary/10">
          <Globe className="h-10 w-10 text-primary" />
        </div>
        <div className="absolute -top-1 -right-1 flex items-center justify-center w-8 h-8 rounded-full bg-muted border-2 border-background">
          <Search className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="absolute -bottom-1 -left-1 flex items-center justify-center w-8 h-8 rounded-full bg-muted border-2 border-background">
          <TrendingUp className="h-4 w-4 text-muted-foreground" />
        </div>
      </div>
      <h3 className="text-lg font-semibold mb-2">{t('marketTracker.emptyTitle')}</h3>
      <p className="text-sm text-muted-foreground text-center max-w-md mb-4">
        {t('marketTracker.emptyDesc')}
      </p>
      <p className="text-xs text-muted-foreground/70 text-center max-w-sm">
        {t('marketTracker.emptyTip')}
      </p>
    </div>
  )
}
