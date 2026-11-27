import type { QualityRuleKey, QualityRuleResult, QualityState } from '@/types'

type T = (key: string, vars?: Record<string, string | number>) => string

export interface ResultDescription {
  /** Translated message(s): the main finding first, then any further issues. */
  messages: string[]
  /** Measured values from the rule details, ready to display as "label: value". */
  measured: Array<{ label: string; value: string }>
  /** Checks the rule could not run (no main keyword, no brand, image text). */
  notes: string[]
}

export const ruleLabel = (t: T, key: QualityRuleKey | string) => t(`cm.rule.${key}`)
export const stateLabel = (t: T, state: QualityState) => t(`cm.state.${state}`)

const asNumber = (v: unknown): number | undefined =>
  typeof v === 'number' && Number.isFinite(v) ? v : undefined

const asList = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []

const asText = (v: unknown): string | undefined =>
  typeof v === 'string' && v.trim() ? v : undefined

const pct = (v: unknown): string => {
  const n = asNumber(v)
  return n === undefined ? '—' : String(Math.round(n * 100))
}

function messageVars(result: QualityRuleResult): Record<string, string | number> {
  const d = result.details
  const num = (k: string) => asNumber(d[k]) ?? '—'
  // main_image reports ratios (0..1); everything else reports plain counts
  const isRatio = result.key === 'main_image'
  return {
    length: num('length'),
    limit: isRatio ? pct(d.limit) : num('limit'),
    count: num('count'),
    target: num('target'),
    modules: num('modules'),
    bytes: num('bytes'),
    fill: pct(d.fill_ratio),
    missing: asList(d.missing).join(', ') || '—',
    path: asText(d.path) ?? '—',
    expected: asList(d.expected).join(', ') || '—',
    error: asText(d.error) ?? '—',
  }
}

export function describeResult(t: T, result: QualityRuleResult): ResultDescription {
  const vars = messageVars(result)
  const d = result.details
  const keyFor = (code: string) => `cm.code.${result.key}.${code}`
  const translate = (code: string) => {
    const key = keyFor(code)
    const text = t(key, vars)
    return text === key ? t('cm.code.unknown', { code }) : text
  }

  const messages = [translate(result.code)]
  // The title rule lists every problem it found, the code is only the first.
  for (const extra of asList(d.issues)) {
    if (extra !== result.code) messages.push(translate(extra))
  }

  const measured: ResultDescription['measured'] = []
  const add = (labelKey: string, value: string | undefined) => {
    if (value !== undefined) measured.push({ label: t(`cm.measure.${labelKey}`), value })
  }
  const withLimit = (value: unknown, limit: string | number) =>
    asNumber(value) === undefined ? undefined : `${value} / ${limit}`
  const limit = result.key === 'main_image' ? `${pct(d.limit)}%` : String(asNumber(d.limit) ?? '—')
  const target = String(asNumber(d.target) ?? '—')
  add('length', withLimit(d.length, limit))
  add('count', withLimit(d.count, target))
  add('modules', withLimit(d.modules, target))
  add('aplusText', asNumber(d.text_module_count)?.toString())
  add('aplusImages', asNumber(d.image_module_count)?.toString())
  add('aplusComparisons', asNumber(d.comparison_module_count)?.toString())
  add('bytes', withLimit(d.bytes, limit))
  if (asNumber(d.fill_ratio) !== undefined) add('fill', `${pct(d.fill_ratio)}% / ${limit}`)
  if (asList(d.missing).length) add('missing', asList(d.missing).join(', '))
  add('path', asText(d.path))

  const notes: string[] = []
  if (d.keyword_checked === false) notes.push(t('cm.note.keywordNotChecked'))
  if (d.brand_checked === false) notes.push(t('cm.note.brandNotChecked'))
  if (d.text_checked === false) notes.push(t('cm.note.textNotChecked'))

  return { messages, measured, notes }
}

/** One plain-text line for a native tooltip: finding, measured values, notes. */
export function resultTooltip(t: T, result: QualityRuleResult): string {
  const { messages, notes } = describeResult(t, result)
  return [...messages, ...notes].join(' · ')
}
