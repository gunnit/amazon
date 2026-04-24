import type { AccountStatus, SyncStatus } from '@/types'

export const DASHBOARD_ACCOUNT_PARAM = 'account'

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export type DashboardScope =
  | { mode: 'all' }
  | { mode: 'resolving'; requestedAccountId: string }
  | { mode: 'invalid'; requestedAccountId: string }
  | { mode: 'missing'; requestedAccountId: string }
  | {
      mode: 'account'
      accountId: string
      accountName: string
      marketplace: string
      status: SyncStatus
      syncErrorMessage: string | null
    }

export function isValidAccountParam(value: string | null): value is string {
  return value != null && UUID_PATTERN.test(value)
}

export function resolveDashboardScope(
  requestedAccountId: string | null,
  accounts?: AccountStatus[]
): DashboardScope {
  if (!requestedAccountId) {
    return { mode: 'all' }
  }

  if (!isValidAccountParam(requestedAccountId)) {
    return { mode: 'invalid', requestedAccountId }
  }

  if (!accounts) {
    return { mode: 'resolving', requestedAccountId }
  }

  const account = accounts.find((item) => item.id === requestedAccountId)

  if (!account) {
    return { mode: 'missing', requestedAccountId }
  }

  return {
    mode: 'account',
    accountId: account.id,
    accountName: account.account_name,
    marketplace: account.marketplace_country,
    status: account.sync_status,
    syncErrorMessage: account.sync_error_message,
  }
}

export function buildDashboardSearchParams(
  currentSearchParams: URLSearchParams,
  accountId?: string | null
): URLSearchParams {
  const nextSearchParams = new URLSearchParams(currentSearchParams)

  if (accountId) {
    nextSearchParams.set(DASHBOARD_ACCOUNT_PARAM, accountId)
  } else {
    nextSearchParams.delete(DASHBOARD_ACCOUNT_PARAM)
  }

  return nextSearchParams
}
