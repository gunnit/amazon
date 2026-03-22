import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTranslation } from '@/i18n'

const FALLBACK_CATEGORIES = ['Electronics', 'Sports', 'Home & Kitchen', 'Grocery', 'Beauty', 'Toys']

interface CategoryFilterProps {
  value: string
  onChange: (value: string) => void
  options?: string[]
}

export function CategoryFilter({ value, onChange, options }: CategoryFilterProps) {
  const { t } = useTranslation()
  const categories = options && options.length > 0 ? options : FALLBACK_CATEGORIES
  return (
    <Select value={value || '_all'} onValueChange={(v) => onChange(v === '_all' ? '' : v)}>
      <SelectTrigger className="w-[160px] h-9 text-sm">
        <SelectValue placeholder={t('filter.allCategories')} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="_all">{t('filter.allCategories')}</SelectItem>
        {categories.map((cat) => (
          <SelectItem key={cat} value={cat}>
            {cat}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
