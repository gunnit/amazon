import { useEffect, useMemo } from 'react'
import { Navigate, useLocation, useParams } from 'react-router-dom'
import { useTranslation } from '@/i18n'
import { DocsNav } from '@/components/docs/DocsNav'
import { getDoc, getDocGroups, getDocs } from '@/components/docs/registry'

// Black-and-white reading column: hierarchy from type and space, colours from
// the app's theme tokens so it survives the dark theme.
const prose = [
  'text-[15px] leading-7 text-foreground/90',
  '[&_h2]:mt-12 [&_h2]:scroll-mt-24 [&_h2]:border-t [&_h2]:border-foreground/15 [&_h2]:pt-6 [&_h2]:font-mono [&_h2]:text-xs [&_h2]:font-semibold [&_h2]:uppercase [&_h2]:tracking-[0.22em] [&_h2]:text-foreground',
  '[&_h3]:mt-8 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-foreground [&_h3]:scroll-mt-24',
  '[&_p]:mt-4',
  '[&_ul]:mt-4 [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5',
  '[&_ol]:mt-4 [&_ol]:list-decimal [&_ol]:space-y-1.5 [&_ol]:pl-5',
  '[&_a]:underline [&_a]:underline-offset-2 [&_a]:decoration-foreground/30 hover:[&_a]:decoration-foreground',
  '[&_strong]:font-semibold [&_strong]:text-foreground',
  '[&_code]:rounded-sm [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[13px]',
  '[&_pre]:mt-4 [&_pre]:overflow-x-auto [&_pre]:border [&_pre]:border-foreground/15 [&_pre]:bg-muted/40 [&_pre]:p-4 [&_pre_code]:bg-transparent [&_pre_code]:p-0',
  '[&_blockquote]:mt-6 [&_blockquote]:border-l-2 [&_blockquote]:border-foreground/25 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground',
  '[&_hr]:my-10 [&_hr]:border-foreground/15',
  '[&_table]:mt-6 [&_table]:w-full [&_table]:border-collapse',
  '[&_th]:border-b [&_th]:border-foreground/25 [&_th]:py-2 [&_th]:pr-4 [&_th]:text-left [&_th]:font-mono [&_th]:text-[10px] [&_th]:font-semibold [&_th]:uppercase [&_th]:tracking-[0.14em] [&_th]:text-muted-foreground',
  '[&_td]:border-b [&_td]:border-foreground/10 [&_td]:py-2 [&_td]:pr-4 [&_td]:align-top [&_td]:text-sm',
].join(' ')

export default function Docs() {
  const { slug } = useParams()
  const { hash } = useLocation()
  const { t, language } = useTranslation()

  const docs = useMemo(() => getDocs(language), [language])
  const groups = useMemo(() => getDocGroups(language), [language])
  const doc = getDoc(slug, language)

  useEffect(() => {
    if (!doc) return
    const target = hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    else window.scrollTo({ top: 0 })
  }, [doc, hash])

  if (!slug && docs.length > 0) {
    return <Navigate to={`/docs/${docs[0].slug}`} replace />
  }

  return (
    <div className="pb-4">
      <header className="ba-rise">
        <div aria-hidden="true" className="border-t-[3px] border-foreground" />
        <div aria-hidden="true" className="mt-[3px] border-t border-foreground/30" />
        <div className="pt-6">
          <h1 className="text-3xl font-bold tracking-tight">{doc?.title ?? t('docs.title')}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            {t('docs.subtitle')}
          </p>
        </div>
      </header>

      {docs.length === 0 ? (
        <p className="mt-10 text-sm text-muted-foreground">{t('docs.empty')}</p>
      ) : (
        <div className="mt-8 gap-12 lg:flex lg:items-start">
          {/* Mobile: native disclosure, closed again on every navigation. */}
          <details key={slug} className="mb-6 border-y border-foreground/15 py-3 lg:hidden">
            <summary className="cursor-pointer font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
              {t('docs.index')}
            </summary>
            <div className="pt-4">
              <DocsNav groups={groups} activeSlug={slug} />
            </div>
          </details>

          <aside className="hidden w-56 shrink-0 lg:sticky lg:top-24 lg:block lg:max-h-[calc(100vh-8rem)] lg:overflow-y-auto">
            <DocsNav groups={groups} activeSlug={slug} />
          </aside>

          <article className={`min-w-0 max-w-[70ch] flex-1 overflow-x-auto ${prose}`}>
            {doc ? (
              <div dangerouslySetInnerHTML={{ __html: doc.html }} />
            ) : (
              <p className="text-sm text-muted-foreground">{t('docs.notFound')}</p>
            )}
          </article>
        </div>
      )}
    </div>
  )
}
