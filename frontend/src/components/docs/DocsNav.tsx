import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { eyebrow } from '@/lib/editorial'
import { useTranslation } from '@/i18n'
import type { Doc } from './registry'

export function DocsNav({
  groups,
  activeSlug,
  onNavigate,
}: {
  groups: { key: string; docs: Doc[] }[]
  activeSlug?: string
  onNavigate?: () => void
}) {
  const { t } = useTranslation()

  return (
    <nav className="space-y-6 text-sm">
      {groups.map((group) => (
        <div key={group.key}>
          <p className={cn(eyebrow, 'pb-3')}>{t(group.key)}</p>
          <ul className="space-y-0.5">
            {group.docs.map((doc) => {
          const isActive = doc.slug === activeSlug
          return (
            <li key={doc.slug}>
              <Link
                to={`/docs/${doc.slug}`}
                onClick={onNavigate}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'block border-l-2 py-1.5 pl-3 transition-colors',
                  isActive
                    ? 'border-foreground font-medium text-foreground'
                    : 'border-transparent text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                )}
              >
                {doc.title}
              </Link>
              {isActive && doc.sections.length > 0 && (
                <ul className="mb-2 mt-1 space-y-0.5 border-l-2 border-foreground/15 pl-3">
                  {doc.sections.map((section) => (
                    <li key={section.id}>
                      <Link
                        to={`/docs/${doc.slug}#${section.id}`}
                        onClick={onNavigate}
                        className="block py-1 text-[13px] leading-5 text-muted-foreground hover:text-foreground"
                      >
                        {section.text}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )
}
