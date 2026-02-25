import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { GroupBy } from '@/store/filterStore'

interface GroupByFilterProps {
  value: GroupBy
  onChange: (value: GroupBy) => void
}

export function GroupByFilter({ value, onChange }: GroupByFilterProps) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as GroupBy)}>
      <SelectTrigger className="w-[120px] h-9 text-sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="day">Day</SelectItem>
        <SelectItem value="week">Week</SelectItem>
        <SelectItem value="month">Month</SelectItem>
      </SelectContent>
    </Select>
  )
}
