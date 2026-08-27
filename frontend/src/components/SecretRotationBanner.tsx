import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { KeyRound } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { accountsApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import type { AmazonAccount } from '@/types'

const STEPS = ['secretRotation.step1', 'secretRotation.step2', 'secretRotation.step3', 'secretRotation.step4']

/**
 * Amazon forces a client-secret rotation every 180 days; once it lapses every
 * sync 403s. The only other warning channel is email, so this has to be loud
 * and in-app.
 */
export function SecretRotationBanner() {
  const { t } = useTranslation()
  const { data: accounts = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const affected = accounts.filter((account) => account.sync_error_code === 'LWA_SECRET_EXPIRED')
  if (affected.length === 0) return null

  return (
    <Alert variant="destructive">
      <KeyRound className="h-4 w-4" />
      <AlertTitle>{t('secretRotation.title')}</AlertTitle>
      <AlertDescription className="space-y-3">
        <p>{t('secretRotation.intro')}</p>
        <div>
          <p className="font-medium">{t('secretRotation.stepsTitle')}</p>
          <ol className="mt-1 list-decimal space-y-1 pl-5">
            {STEPS.map((step) => <li key={step}>{t(step)}</li>)}
          </ol>
        </div>
        <p>{t('secretRotation.reassurance')}</p>
        <p className="text-xs">
          {t('secretRotation.affected', {
            accounts: affected.map((account) => account.account_name).join(', '),
          })}
        </p>
        <Button asChild size="sm" variant="outline">
          <Link to="/settings">{t('secretRotation.cta')}</Link>
        </Button>
      </AlertDescription>
    </Alert>
  )
}

export default SecretRotationBanner
