import { useEffect } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTranslation } from '@/i18n'
import type { GroupBy } from '@/store/filterStore'
import type { Granularity } from '@/lib/granularity'

interface GroupByFilterProps {
  value: GroupBy
  onChange: (value: GroupBy) => void
  granularity?: Granularity
}

// On monthly (vendor) data, day and week buckets are incoherent, so we force a
// monthly grouping and disable the finer options instead of letting the user
// pick a cadence the data can't support.
export function GroupByFilter({ value, onChange, granularity }: GroupByFilterProps) {
  const { t } = useTranslation()
  const monthlyOnly = granularity === 'monthly'

  useEffect(() => {
    if (monthlyOnly && value !== 'month') {
      onChange('month')
    }
  }, [monthlyOnly, value, onChange])

  return (
    <Select value={value} onValueChange={(v) => onChange(v as GroupBy)} disabled={monthlyOnly}>
      <SelectTrigger className="w-[120px] h-9 text-sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="day" disabled={monthlyOnly}>{t('filter.day')}</SelectItem>
        <SelectItem value="week" disabled={monthlyOnly}>{t('filter.week')}</SelectItem>
        <SelectItem value="month">{t('filter.month')}</SelectItem>
      </SelectContent>
    </Select>
  )
}
