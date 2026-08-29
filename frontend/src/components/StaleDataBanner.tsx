import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { CloudOff } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { accountsApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import { formatLocalizedDate } from '@/lib/utils'
import type { AmazonAccount } from '@/types'

/**
 * Ingestion once stopped for 16 days without anyone noticing: the only
 * notification channel is email, and email cannot be delivered. This banner is
 * the channel that always works, and unlike SecretRotationBanner it keys off
 * the AGE of the last successful sync rather than a specific error code, so it
 * fires whatever the cause — expired credential, dead scheduler, revoked
 * token, an Amazon report that silently returns nothing.
 */
const STALE_AFTER_HOURS = 48

export function StaleDataBanner() {
  const { t, language } = useTranslation()
  const { data: accounts = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const now = Date.now()
  const stale = accounts.filter((account) => {
    if (!account.is_active || !account.has_refresh_token) return false
    // Never synced at all is a setup state, not a stall — Accounts covers it.
    if (!account.last_sync_succeeded_at) return false
    const ageHours = (now - new Date(account.last_sync_succeeded_at).getTime()) / 3_600_000
    return ageHours > STALE_AFTER_HOURS
  })

  if (stale.length === 0) return null

  const oldest = stale.reduce((a, b) =>
    new Date(a.last_sync_succeeded_at!) < new Date(b.last_sync_succeeded_at!) ? a : b
  )

  return (
    <Alert variant="destructive">
      <CloudOff className="h-4 w-4" />
      <AlertTitle>{t('staleData.title')}</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>{t('staleData.intro', { n: stale.length })}</p>
        <ul className="list-disc space-y-1 pl-5">
          {stale.map((account) => (
            <li key={account.id}>
              <span className="font-medium">{account.account_name}</span>
              {' — '}
              {formatLocalizedDate(account.last_sync_succeeded_at!, language)}
              {account.sync_error_message ? ` (${account.sync_error_message})` : ''}
            </li>
          ))}
        </ul>
        <p className="text-xs">
          {t('staleData.hint', {
            date: formatLocalizedDate(oldest.last_sync_succeeded_at!, language),
          })}
        </p>
        <Button asChild size="sm" variant="outline">
          <Link to="/settings?tab=accounts">{t('staleData.cta')}</Link>
        </Button>
      </AlertDescription>
    </Alert>
  )
}
