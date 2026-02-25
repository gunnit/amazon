import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const CATEGORIES = ['Electronics', 'Sports', 'Home & Kitchen', 'Grocery', 'Beauty', 'Toys']

interface CategoryFilterProps {
  value: string
  onChange: (value: string) => void
}

export function CategoryFilter({ value, onChange }: CategoryFilterProps) {
  return (
    <Select value={value || '_all'} onValueChange={(v) => onChange(v === '_all' ? '' : v)}>
      <SelectTrigger className="w-[160px] h-9 text-sm">
        <SelectValue placeholder="All categories" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="_all">All categories</SelectItem>
        {CATEGORIES.map((cat) => (
          <SelectItem key={cat} value={cat}>
            {cat}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
