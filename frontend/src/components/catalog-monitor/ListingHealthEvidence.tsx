import { useTranslation } from '@/i18n'
import type { ListingHealth } from '@/types'

type Props = { health?: ListingHealth | null }

function observedTime(value: string, language: string) {
  return new Date(value).toLocaleString(language === 'it' ? 'it-IT' : 'en-GB', {
    dateStyle: 'medium', timeStyle: 'short',
  })
}

export function ListingHealthSummary({ health }: Props) {
  const { t, language } = useTranslation()
  if (!health) return <span className="text-muted-foreground">{t('cm.health.unavailable')}</span>
  const flags = health.statuses_read ? health.statuses : null
  const issues = health.issues_read ? health.issues : null
  const labels = []
  if (flags !== null) {
    if (health.buyability_applicable) labels.push(t(flags.includes('BUYABLE') ? 'cm.health.buyable' : 'cm.health.unbuyable'))
    if (!flags.includes('DISCOVERABLE') || !health.buyability_applicable) {
      labels.push(t(flags.includes('DISCOVERABLE') ? 'cm.health.discoverable' : 'cm.health.notDiscoverable'))
    }
  }
  if (issues?.length) labels.push(t('cm.health.issueCount', { n: issues.length }))
  if (!labels.length) labels.push(t(issues ? 'cm.health.noIssues' : 'cm.health.unavailable'))
  return (
    <div>
      <div>{labels.join(' · ')}</div>
      <div className="text-muted-foreground">{observedTime(health.checked_at, language)}</div>
    </div>
  )
}

export function ListingHealthEvidence({ health }: Props) {
  const { t, language } = useTranslation()
  function observation(stamp: string | null, read: boolean) {
    if (!stamp) return t('cm.health.unavailable')
    return t(read ? 'cm.health.observed' : 'cm.health.historical', {
      time: observedTime(stamp, language),
    })
  }
  return (
    <section className="space-y-3 rounded-md border p-3 text-sm">
      <h3 className="font-semibold">{t('cm.health.title')}</h3>
      {!health ? <p className="text-muted-foreground">{t('cm.health.requiresScan')}</p> : (
        <>
          <p className="text-xs text-muted-foreground">
            {t('cm.health.checked', { time: observedTime(health.checked_at, language) })}
          </p>
          <div>
            <p className="font-medium">{t('cm.health.offerStatus')}</p>
            <p className="text-xs text-muted-foreground">{observation(health.statuses_observed_at, health.statuses_read)}</p>
            {health.statuses !== null && (
              <p>{[
                health.buyability_applicable && t(health.statuses.includes('BUYABLE') ? 'cm.health.buyable' : 'cm.health.unbuyable'),
                t(health.statuses.includes('DISCOVERABLE') ? 'cm.health.discoverable' : 'cm.health.notDiscoverable'),
              ].filter(Boolean).join(' · ')}</p>
            )}
            {!health.buyability_applicable && <p className="text-xs text-muted-foreground">{t('cm.health.vendorBuyability')}</p>}
          </div>
          <div>
            <p className="font-medium">{t('cm.health.issues')}</p>
            <p className="text-xs text-muted-foreground">{observation(health.issues_observed_at, health.issues_read)}</p>
            {health.issues?.length === 0 && <p>{t('cm.health.noIssues')}</p>}
            {!!health.issues?.length && (
              <ul className="mt-2 divide-y">
                {health.issues.map((issue, index) => (
                  <li className="space-y-1 py-2" key={index}>
                    <div className="font-medium">{[issue.severity, issue.code].filter(Boolean).join(' · ')}</div>
                    {issue.message && <p>{issue.message}</p>}
                    {issue.attributes.length > 0 && <p className="font-mono text-xs">{issue.attributes.join(', ')}</p>}
                    {issue.actions.length > 0 && (
                      <p className="text-xs">{[...issue.actions, issue.exemption].filter(Boolean).join(' · ')}</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  )
}
