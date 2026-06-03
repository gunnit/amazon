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
