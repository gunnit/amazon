import type { AccountType } from '@/types'

// Vendor Central reports monthly, Seller Central daily. A view that mixes both
// has to plot each series on its own cadence, so the UI resolves the natural
// granularity of the in-scope accounts and adapts charts and the group-by.
export type Granularity = 'daily' | 'monthly' | 'mixed' | 'unknown'

export function granularityForAccountTypes(
  accountTypes: Iterable<AccountType>
): Granularity {
  let hasSeller = false
  let hasVendor = false
  for (const type of accountTypes) {
    if (type === 'vendor') hasVendor = true
    else if (type === 'seller') hasSeller = true
  }

  if (hasSeller && hasVendor) return 'mixed'
  if (hasVendor) return 'monthly'
  if (hasSeller) return 'daily'
  return 'unknown'
}

interface AccountLike {
  id: string
  account_type: AccountType
}

// Format a period bucket for tables/axes. Monthly buckets (vendor cadence) show
// month/year so a row dated the 1st isn't misread as a single day's sales.
export function formatPeriodLabel(
  value: string,
  groupBy: 'day' | 'week' | 'month',
  language: 'en' | 'it'
): string {
  const locale = language === 'it' ? 'it-IT' : 'en-US'
  const date = new Date(`${value}T00:00:00`)
  if (groupBy === 'month') {
    return date.toLocaleDateString(locale, { month: 'short', year: 'numeric' })
  }
  return date.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })
}

// On a monthly view, missing months should read as 0, not vanish. Fill the gaps
// between the first and last present month so a zeroed month stays on the line.
export function fillMonthlyGaps<T extends { date: string }>(
  rows: T[],
  makeZero: (monthKey: string) => T
): T[] {
  if (rows.length === 0) return rows
  const byMonth = new Map<string, T>()
  for (const row of rows) byMonth.set(row.date.slice(0, 7) + '-01', row)
  const keys = Array.from(byMonth.keys()).sort()
  const [first, last] = [keys[0], keys[keys.length - 1]]
  const out: T[] = []
  const cursor = new Date(`${first}T00:00:00`)
  const end = new Date(`${last}T00:00:00`)
  while (cursor <= end) {
    const key = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}-01`
    out.push(byMonth.get(key) ?? makeZero(key))
    cursor.setMonth(cursor.getMonth() + 1)
  }
  return out
}

// Resolve granularity from the full account list and the selected ids. An empty
// selection means "all accounts", matching how the analytics filters behave.
export function granularityForSelection(
  accounts: AccountLike[] | undefined,
  selectedAccountIds: string[]
): Granularity {
  if (!accounts || accounts.length === 0) return 'unknown'
  const inScope =
    selectedAccountIds.length === 0
      ? accounts
      : accounts.filter((account) => selectedAccountIds.includes(account.id))
  return granularityForAccountTypes(inScope.map((account) => account.account_type))
}
