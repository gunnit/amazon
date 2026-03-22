import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTranslation } from '@/i18n'
import type { GroupBy } from '@/store/filterStore'

interface GroupByFilterProps {
  value: GroupBy
  onChange: (value: GroupBy) => void
}

export function GroupByFilter({ value, onChange }: GroupByFilterProps) {
  const { t } = useTranslation()
  return (
    <Select value={value} onValueChange={(v) => onChange(v as GroupBy)}>
      <SelectTrigger className="w-[120px] h-9 text-sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="day">{t('filter.day')}</SelectItem>
        <SelectItem value="week">{t('filter.week')}</SelectItem>
        <SelectItem value="month">{t('filter.month')}</SelectItem>
      </SelectContent>
    </Select>
  )
}
