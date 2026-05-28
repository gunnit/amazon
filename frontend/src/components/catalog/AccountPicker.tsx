import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Label } from '@/components/ui/label'
import type { TabProps } from './types'

export function AccountPicker({ accountId, accounts, onAccountChange, t }: TabProps) {
  return (
    <div className="space-y-1">
      <Label>{t('catalog.products.account')}</Label>
      <Select value={accountId} onValueChange={onAccountChange}>
        <SelectTrigger>
          <SelectValue placeholder={t('catalog.products.selectAccount')} />
        </SelectTrigger>
        <SelectContent>
          {accounts.map((acc) => (
            <SelectItem key={acc.id} value={acc.id}>
              {acc.account_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
