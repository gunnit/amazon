import { useCallback } from 'react'
import { useLanguageStore } from '@/store/languageStore'
import type { Language } from '@/store/languageStore'
import en from './en'
import it from './it'

const locales: Record<Language, Record<string, string>> = { en, it }

/**
 * Simple interpolation: replaces `{key}` tokens in a translated string.
 *   t('dashboard.revenueTrendDesc', { days: '30' })
 *   => "Daily revenue over the 30"
 */
function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (_, key) =>
    vars[key] !== undefined ? String(vars[key]) : `{${key}}`,
  )
}

export function useTranslation() {
  const { language, setLanguage } = useLanguageStore()

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const value = locales[language]?.[key] ?? locales.en[key] ?? key
      return interpolate(value, vars)
    },
    [language],
  )

  return { t, language, setLanguage } as const
}
