import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTranslation } from '@/i18n'

interface BrandFilterProps {
  value: string
  onChange: (value: string) => void
  options: string[]
}

export function BrandFilter({ value, onChange, options }: BrandFilterProps) {
  const { t } = useTranslation()
  return (
    <Select value={value || '_all'} onValueChange={(v) => onChange(v === '_all' ? '' : v)}>
      <SelectTrigger className="w-[160px] h-9 text-sm">
        <SelectValue placeholder={t('filter.allBrands')} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="_all">{t('filter.allBrands')}</SelectItem>
        {options.map((brand) => (
          <SelectItem key={brand} value={brand}>
            {brand}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
