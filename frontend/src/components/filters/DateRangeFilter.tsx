import { useState } from 'react'
import { CalendarIcon } from 'lucide-react'
import { format } from 'date-fns'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Calendar } from '@/components/ui/calendar'
import { useFilterStore } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import type { DatePreset } from '@/store/filterStore'
import type { DateRange } from 'react-day-picker'

const PRESET_KEYS: { value: DatePreset; key: string }[] = [
  { value: '7', key: 'filter.last7days' },
  { value: '14', key: 'filter.last14days' },
  { value: '30', key: 'filter.last30days' },
  { value: '60', key: 'filter.last60days' },
  { value: '90', key: 'filter.last90days' },
  { value: 'custom', key: 'filter.customRange' },
]

export function DateRangeFilter() {
  const { datePreset, customStartDate, customEndDate, setDatePreset, setCustomDateRange } =
    useFilterStore()
  const [calendarOpen, setCalendarOpen] = useState(false)
  const { t } = useTranslation()

  const handlePresetChange = (value: string) => {
    if (value === 'custom') {
      setCalendarOpen(true)
      setDatePreset('custom')
    } else {
      setDatePreset(value as DatePreset)
    }
  }

  const handleDateSelect = (range: DateRange | undefined) => {
    if (range?.from && range?.to) {
      const start = format(range.from, 'yyyy-MM-dd')
      const end = format(range.to, 'yyyy-MM-dd')
      setCustomDateRange(start, end)
      setCalendarOpen(false)
    }
  }

  const displayLabel =
    datePreset === 'custom' && customStartDate && customEndDate
      ? `${format(new Date(customStartDate + 'T00:00:00'), 'MMM d')} - ${format(new Date(customEndDate + 'T00:00:00'), 'MMM d')}`
      : undefined

  const calendarFrom = customStartDate ? new Date(customStartDate + 'T00:00:00') : undefined
  const calendarTo = customEndDate ? new Date(customEndDate + 'T00:00:00') : undefined

  return (
    <div className="flex items-center gap-2">
      <Select value={datePreset} onValueChange={handlePresetChange}>
        <SelectTrigger className="w-[170px] h-9 text-sm">
          <CalendarIcon className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
          <SelectValue>
            {displayLabel || t(PRESET_KEYS.find((p) => p.value === datePreset)?.key || '')}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {PRESET_KEYS.map((preset) => (
            <SelectItem key={preset.value} value={preset.value}>
              {t(preset.key)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {datePreset === 'custom' && (
        <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="h-9 text-xs">
              {customStartDate && customEndDate
                ? `${format(new Date(customStartDate + 'T00:00:00'), 'MMM d, yyyy')} - ${format(new Date(customEndDate + 'T00:00:00'), 'MMM d, yyyy')}`
                : t('filter.pickDates')}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="range"
              selected={{ from: calendarFrom, to: calendarTo }}
              onSelect={handleDateSelect}
              numberOfMonths={2}
              disabled={{ after: new Date() }}
            />
          </PopoverContent>
        </Popover>
      )}
    </div>
  )
}
