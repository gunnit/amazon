// Backend HTTPException details are English prose and pydantic 422 details are
// arrays, so piping `response.data.detail` straight into a toast description
// either shows English under an Italian title or renders "[object Object]".
// Known details map to an i18n key; anything else is dropped so the toast keeps
// its localized title alone.
const DETAIL_KEYS: Record<string, string> = {
  'account not found': 'apiError.accountNotFound',
  'account not found or does not belong to organization': 'apiError.accountNotFound',
  'one or more account ids are invalid': 'apiError.accountNotFound',
  'product not found': 'apiError.productNotFound',
  'report not found': 'apiError.reportNotFound',
  'competitor not found': 'apiError.competitorNotFound',
  'competitor is already tracked': 'apiError.competitorDuplicate',
  'invalid asin format': 'apiError.invalidAsin',
  'only completed reports can be refreshed': 'apiError.reportNotCompleted',
  'report has no competitor data to refresh': 'apiError.reportNoCompetitors',
  'report artifact is not ready': 'apiError.artifactNotReady',
  'missing refresh token': 'apiError.missingCredentials',
  'provide an advertising refresh token or an account with ads credentials':
    'apiError.missingAdsCredentials',
  'start_date must be on or before end_date': 'apiError.invalidDateRange',
  'start_date cannot be after end_date': 'apiError.invalidDateRange',
  'period_start must be on or before period_end': 'apiError.invalidDateRange',
  'amazon api rate limited. please try again in a few seconds.': 'apiError.rateLimited',
  'no files uploaded': 'apiError.noFiles',
  'email already registered': 'apiError.emailTaken',
  'image storage is unavailable': 'apiError.imageStorageUnavailable',
  'image updates are only available for seller central accounts': 'apiError.sellerOnly',
  // catalogue monitor (R2-R4); upload messages come in Italian, matched on the part before the colon
  'administrator role required': 'apiError.adminRequired',
  'file troppo grande': 'apiError.fileTooLarge',
  'formato del file non supportato': 'apiError.fileFormat',
  'impossibile leggere il file': 'apiError.fileUnreadable',
  'definizione del tipo di prodotto non disponibile': 'apiError.productTypeUnavailable',
  'no approved file-only requests in batch': 'apiError.noFeedRequests',
  'anomalies not found': 'apiError.anomalyNotFound',
  'anomaly not found': 'apiError.anomalyNotFound',
  'anomaly is resolved': 'apiError.anomalyHandled',
  'anomaly is restore_requested': 'apiError.anomalyHandled',
  'variation family not found': 'apiError.familyNotFound',
  'no amazon account in scope': 'apiError.noAccountInScope',
}

// Details that carry a number: matched by pattern, the number goes into the message.
const DETAIL_PATTERNS: Array<[RegExp, string]> = [
  [/^il file contiene (\d+) modifiche/i, 'apiError.tooManyChanges'],
]

function rawDetail(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof detail === 'string' ? detail : null
}

/** Localized description for an API error, or undefined when we have none. */
export function apiErrorDetail(
  error: unknown,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string | undefined {
  const detail = rawDetail(error)
  if (!detail) return undefined
  const key = DETAIL_KEYS[detail.trim().toLowerCase()]
  if (key) return t(key)
  for (const [pattern, patternKey] of DETAIL_PATTERNS) {
    const match = pattern.exec(detail.trim())
    if (match) return t(patternKey, { count: match[1] })
  }
  // Some backends prefix a cause: match on the known head before the colon.
  const head = detail.split(':')[0].trim().toLowerCase()
  const headKey = DETAIL_KEYS[head]
  return headKey ? t(headKey) : undefined
}
