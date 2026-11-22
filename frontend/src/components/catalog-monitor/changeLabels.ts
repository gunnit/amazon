import type {
  AnomalyStatus,
  CatalogAnomaly,
  ChangeIssue,
  ChangeKind,
  ChangeRequest,
  ChangeRequestStatus,
} from '@/types'
import { CHANGE_REQUEST_STATUSES } from '@/types'

type T = (key: string, vars?: Record<string, string | number>) => string

const IMAGE_SLOT = /^other_product_image_locator_(\d+)$/
const ANOMALY_STATUSES: AnomalyStatus[] = ['open', 'acknowledged', 'restore_requested', 'resolved']

/** Requests the operator still has to act on: approve, send or download. */
export const AWAITING_ACTION: ChangeRequestStatus[] = ['valid', 'file_only', 'approved']

const translated = (t: T, key: string, fallback: string, vars?: Record<string, string | number>) => {
  const text = t(key, vars)
  return text === key ? fallback : text
}

/** title|bullets|description|images|aplus|attribute:<name>|parent:<ASIN>|image slot attribute. */
export function fieldLabel(t: T, field: string): string {
  if (field.startsWith('attribute:')) return t('cm.field.attribute', { name: field.slice(10) })
  if (field.startsWith('parent:')) return t('cm.field.family', { asin: field.slice(7) })
  if (field === 'main_product_image_locator') return t('cm.field.mainImage')
  const slot = IMAGE_SLOT.exec(field)
  if (slot) return t('cm.field.imageSlot', { n: slot[1] })
  return translated(t, `cm.field.${field}`, field)
}

export const isImageSlot = (field: string) =>
  field === 'main_product_image_locator' || IMAGE_SLOT.test(field)

export const changeTypeLabel = (t: T, type: string) => translated(t, `cm.change.${type}`, type)
export const anomalyStatusLabel = (t: T, status: string) =>
  translated(t, `cm.anomalyStatus.${status}`, status)
export const requestStatusLabel = (t: T, status: string) =>
  translated(t, `cm.request.status.${status}`, status)
export const kindLabel = (t: T, kind: ChangeKind | string) =>
  translated(t, `cm.request.kind.${kind}`, kind)

/** Why a request or an anomaly was left out of an action (approve, reject, submit, restore). */
export function skipReasonLabel(t: T, reason: string): string {
  if (reason.startsWith('status_')) {
    const status = reason.slice(7)
    const label = (CHANGE_REQUEST_STATUSES as string[]).includes(status)
      ? requestStatusLabel(t, status)
      : (ANOMALY_STATUSES as string[]).includes(status)
        ? anomalyStatusLabel(t, status)
        : status
    return t('cm.skip.status', { status: label })
  }
  return translated(t, `cm.skip.${reason}`, t('cm.skip.unknown', { reason }))
}

/** Badge colours by request status, readable in light and dark mode. */
export const REQUEST_STATUS_CLASS: Record<ChangeRequestStatus, string> = {
  pending: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  valid: 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300',
  invalid: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  approved: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/50 dark:text-indigo-300',
  file_only: 'bg-amber-100 text-amber-900 dark:bg-amber-900/50 dark:text-amber-300',
  submitted: 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300',
  accepted: 'bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300',
  rejected: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
}

const asIssues = (v: unknown): ChangeIssue[] =>
  Array.isArray(v) ? v.filter((i): i is ChangeIssue => !!i && typeof i === 'object') : []

export const isError = (issue: ChangeIssue) => (issue.severity ?? '').toUpperCase() === 'ERROR'

/** Amazon's validation issues followed by those of the submission, if any. */
export function requestIssues(request: ChangeRequest): ChangeIssue[] {
  return [
    ...asIssues(request.validation_issues),
    ...asIssues((request.submission_result ?? {}).issues),
  ]
}

/** Amazon checked the request with VALIDATION_PREVIEW and found no error (as the backend's submit guard). */
export const passedValidation = (request: ChangeRequest) =>
  Array.isArray(request.validation_issues) && !request.validation_issues.some(isError)

/** An approved API request that Invia ad Amazon would really send. */
export const willSubmit = (request: ChangeRequest) =>
  request.status === 'approved' && !request.file_only && passedValidation(request)

export const manualImageRemoval = (request: ChangeRequest): string[] => {
  const paths = request.summary?.manual_image_removal
  return Array.isArray(paths) ? paths.filter((p): p is string => typeof p === 'string') : []
}

export const parentSkuMissing = (request: ChangeRequest) =>
  request.summary?.parent_sku_missing === true

export interface FieldEdit {
  field: string
  before: unknown
  after: unknown
}

const asRecord = (v: unknown): Record<string, unknown> | null =>
  v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null

/**
 * The fields a request changes, before and after, from its summary:
 * content restore {fields: [...], changes: [{field, from, to}]};
 * bulk update and new item {fields: {name: {before, after}}}, images under
 * fields.image_slots {slot attribute: {before, after}}; variation restore has none.
 */
export function requestFields(request: ChangeRequest): FieldEdit[] {
  const summary = request.summary ?? {}
  if (Array.isArray(summary.changes)) {
    return summary.changes
      .map(asRecord)
      .filter((c): c is Record<string, unknown> => c !== null)
      .map((c) => ({ field: String(c.field ?? ''), before: c.from ?? null, after: c.to ?? null }))
  }
  const fields = asRecord(summary.fields)
  if (!fields) return []
  const out: FieldEdit[] = []
  for (const [name, value] of Object.entries(fields)) {
    const edit = asRecord(value)
    if (!edit) continue
    if (name === 'image_slots') {
      for (const [slot, slotEdit] of Object.entries(edit)) {
        const e = asRecord(slotEdit)
        if (e) out.push({ field: slot, before: e.before ?? null, after: e.after ?? null })
      }
    } else {
      // new items list bare attribute names; bulk updates already say attribute:<name>
      const field = request.kind === 'new_item' && !name.includes(':') ? `attribute:${name}` : name
      out.push({ field, before: edit.before ?? null, after: edit.after ?? null })
    }
  }
  return out
}

/** "/attributes/other_product_image_locator_5" -> "other_product_image_locator_5" */
export const pathField = (path: string) => path.split('/').filter(Boolean).pop() ?? path

/** Request statuses that can still go out: while the linked restore has one, it is in progress. */
const LIVE_RESTORE_STATUSES: ChangeRequestStatus[] = ['pending', 'valid', 'file_only', 'approved']

/** A restore that can still go out: no second restore, no accept (backend restore_in_progress). */
export const restoreInProgress = (a: CatalogAnomaly) =>
  a.status === 'restore_requested' &&
  !!a.change_request_status &&
  LIVE_RESTORE_STATUSES.includes(a.change_request_status)

/**
 * Restorable through Amazon: open, or its restore was already sent or ended (an anomaly the
 * scan still sees after an accepted restore must not stay stuck), and not A+ (A+ cannot be
 * written via Listings Items).
 */
export const canRestoreAnomaly = (a: CatalogAnomaly) =>
  (a.status === 'open' ||
    a.status === 'acknowledged' ||
    (a.status === 'restore_requested' && !restoreInProgress(a))) &&
  a.field !== 'aplus'

/** The approvals list returns at most this many requests, newest first (backend _MAX_REQUESTS). */
export const CHANGES_LIST_CAP = 500

/** Sent by the operator by hand on Vendor Central, not through the API. */
export const isManualUpload = (request: ChangeRequest) =>
  request.status === 'submitted' && request.submission_result?.manual === true

/**
 * Goes into the Vendor Central file: a file-only request an admin approved, unless its
 * parent SKU is missing. API requests never travel as a file (backend in_feed_file).
 */
export const inFeedFile = (request: ChangeRequest) =>
  request.status === 'approved' && request.file_only && !parentSkuMissing(request)

/** An approved file-only request still waiting for the operator's manual upload: the file's requests. */
export const awaitsManualUpload = inFeedFile

const OPEN_STATUSES: ChangeRequestStatus[] = ['pending', 'valid', 'file_only', 'approved', 'submitted']

/** Not settled yet: a second request for the same change would duplicate it. */
export const isOpenRequest = (request: ChangeRequest) =>
  OPEN_STATUSES.includes(request.status) && !isManualUpload(request)

/** Approvals filter: what still needs the operator, everything, or one status. */
export type StatusFilter = 'awaiting' | 'all' | ChangeRequestStatus

export const matchesFilter = (filter: StatusFilter, status: ChangeRequestStatus) =>
  filter === 'all' || (filter === 'awaiting' ? AWAITING_ACTION.includes(status) : filter === status)
