import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { accountsApi } from '@/services/api'
import { useFilterStore } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import type { AmazonAccount } from '@/types'

export function AccountFilter() {
  const { accountIds, toggleAccountId, setAccountIds } = useFilterStore()
  const { t } = useTranslation()

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const selectedCount = accountIds.length
  const label =
    selectedCount === 0
      ? t('filter.allAccounts')
      : selectedCount === 1
        ? accounts?.find((a) => a.id === accountIds[0])?.account_name || '1 account'
        : t('filter.nAccounts', { n: selectedCount })

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 text-sm">
          <Building2 className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
          {label}
          <ChevronDown className="ml-2 h-3.5 w-3.5 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3" align="start">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('filter.accounts')}</span>
            {selectedCount > 0 && (
              <button
                className="text-xs text-muted-foreground hover:text-foreground"
                onClick={() => setAccountIds([])}
              >
                {t('common.clear')}
              </button>
            )}
          </div>
          <div className="space-y-2">
            {accounts?.map((account) => (
              <label
                key={account.id}
                className="flex items-center gap-2 cursor-pointer rounded-sm px-1 py-1 hover:bg-accent"
              >
                <Checkbox
                  checked={accountIds.includes(account.id)}
                  onCheckedChange={() => toggleAccountId(account.id)}
                />
                <span className="text-sm flex-1 truncate">{account.account_name}</span>
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  {account.marketplace_country}
                </Badge>
              </label>
            ))}
            {(!accounts || accounts.length === 0) && (
              <p className="text-xs text-muted-foreground py-2">{t('filter.noAccountsFound')}</p>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
