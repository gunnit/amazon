import { useState } from 'react'
import { CalendarIcon } from 'lucide-react'
import { format, subMonths } from 'date-fns'
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
  { value: '12m', key: 'filter.last12months' },
  { value: 'ytd', key: 'filter.yearToDate' },
  { value: 'lastyear', key: 'filter.lastYear' },
  { value: 'custom', key: 'filter.customRange' },
]

export function DateRangeFilter() {
  const { datePreset, customStartDate, customEndDate, setDatePreset, setCustomDateRange } =
    useFilterStore()
  const [calendarOpen, setCalendarOpen] = useState(false)
  // A fresh, in-progress selection. Driving the calendar from this alone (rather
  // than seeding it with the already-applied range) guarantees the first click
  // starts a new range instead of extending the previous one.
  const [pendingRange, setPendingRange] = useState<DateRange | undefined>(undefined)
  const { t } = useTranslation()

  const openCalendar = () => {
    setPendingRange(undefined)
    setCalendarOpen(true)
  }

  const handlePresetChange = (value: string) => {
    if (value === 'custom') {
      setDatePreset('custom')
      // Defer opening the popover so the Select's own dropdown finishes closing.
      // Without this, Radix can treat the Select's close-click as a click-outside
      // for the freshly-mounted Popover and immediately close it again.
      setTimeout(openCalendar, 60)
    } else {
      setCalendarOpen(false)
      setPendingRange(undefined)
      setDatePreset(value as DatePreset)
    }
  }

  const handleCalendarOpenChange = (open: boolean) => {
    if (open) {
      // Always begin a clean selection so a stale range can't be extended.
      setPendingRange(undefined)
    }
    setCalendarOpen(open)
  }

  // Build the range ourselves from the clicked day so behaviour is deterministic:
  // the first click of a new selection starts the range, the second closes it.
  const handleDateSelect = (_range: DateRange | undefined, selectedDay: Date) => {
    const inProgress = pendingRange?.from && !pendingRange?.to
    if (!inProgress) {
      setPendingRange({ from: selectedDay, to: undefined })
      return
    }

    const from = pendingRange!.from!
    const [start, end] = selectedDay < from ? [selectedDay, from] : [from, selectedDay]
    setCustomDateRange(format(start, 'yyyy-MM-dd'), format(end, 'yyyy-MM-dd'))
    setCalendarOpen(false)
    setPendingRange(undefined)
  }

  const displayLabel =
    datePreset === 'custom' && customStartDate && customEndDate
      ? `${format(new Date(customStartDate + 'T00:00:00'), 'MMM d, yyyy')} - ${format(new Date(customEndDate + 'T00:00:00'), 'MMM d, yyyy')}`
      : undefined

  const calendarFrom = pendingRange?.from
  const calendarTo = pendingRange?.to
  const defaultMonth =
    calendarFrom ?? (customStartDate ? new Date(customStartDate + 'T00:00:00') : subMonths(new Date(), 1))

  return (
    <div className="flex items-center gap-2">
      <Select value={datePreset} onValueChange={handlePresetChange}>
        <SelectTrigger className="w-[170px] h-9 text-sm">
          <CalendarIcon className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
          <SelectValue>
            {datePreset === 'custom' && !displayLabel
              ? t('filter.customRange')
              : t(PRESET_KEYS.find((p) => p.value === datePreset)?.key || '')}
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

      {/* Always render the Popover when in custom mode so its mount lifecycle
          doesn't race with the Select close event. */}
      {datePreset === 'custom' && (
        <Popover open={calendarOpen} onOpenChange={handleCalendarOpenChange}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="h-9 text-xs whitespace-nowrap">
              {displayLabel ?? t('filter.pickDates')}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <div className="border-b px-3 py-2 text-xs text-muted-foreground">
              {pendingRange?.from && !pendingRange?.to
                ? t('filter.pickEndDate')
                : t('filter.pickStartDate')}
            </div>
            <Calendar
              mode="range"
              selected={{ from: calendarFrom, to: calendarTo }}
              onSelect={handleDateSelect}
              numberOfMonths={2}
              defaultMonth={defaultMonth}
              disabled={{ after: new Date() }}
            />
          </PopoverContent>
        </Popover>
      )}
    </div>
  )
}
