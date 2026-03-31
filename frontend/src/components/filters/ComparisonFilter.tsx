import { useState } from 'react'
import { format } from 'date-fns'
import { ArrowRightLeft, CalendarRange } from 'lucide-react'
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
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useFilterStore } from '@/store/filterStore'
import { useTranslation } from '@/i18n'
import type { ComparisonMode, ComparisonPreset } from '@/store/filterStore'
import type { DateRange } from 'react-day-picker'

const PRESET_OPTIONS: Array<{ value: ComparisonPreset; labelKey: string }> = [
  { value: 'mom', labelKey: 'comparison.mom' },
  { value: 'qoq', labelKey: 'comparison.qoq' },
  { value: 'yoy', labelKey: 'comparison.yoy' },
]

function ComparisonDateRangeButton({
  label,
  start,
  end,
  onChange,
}: {
  label: string
  start: string | null
  end: string | null
  onChange: (start: string, end: string) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  const selectedRange = {
    from: start ? new Date(start + 'T00:00:00') : undefined,
    to: end ? new Date(end + 'T00:00:00') : undefined,
  }

  const handleSelect = (range: DateRange | undefined) => {
    if (range?.from && range?.to) {
      onChange(format(range.from, 'yyyy-MM-dd'), format(range.to, 'yyyy-MM-dd'))
      setOpen(false)
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 min-w-[185px] justify-start text-xs">
          <CalendarRange className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
          {start && end
            ? `${label}: ${format(new Date(start + 'T00:00:00'), 'MMM d, yyyy')} - ${format(new Date(end + 'T00:00:00'), 'MMM d, yyyy')}`
            : `${label}: ${t('filter.pickDates')}`}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="range"
          selected={selectedRange}
          onSelect={handleSelect}
          numberOfMonths={2}
          disabled={{ after: new Date() }}
        />
      </PopoverContent>
    </Popover>
  )
}

export function ComparisonFilter() {
  const {
    comparisonMode,
    comparisonPreset,
    comparisonPeriod1Start,
    comparisonPeriod1End,
    comparisonPeriod2Start,
    comparisonPeriod2End,
    setComparisonMode,
    setComparisonPreset,
    setComparisonPeriod1Range,
    setComparisonPeriod2Range,
  } = useFilterStore()
  const { t } = useTranslation()

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-border/60 bg-background/80 px-2 py-2">
      <div className="flex items-center gap-2">
        <ArrowRightLeft className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-medium text-muted-foreground">{t('comparison.label')}</span>
      </div>

      <Tabs
        value={comparisonMode}
        onValueChange={(value) => setComparisonMode(value as ComparisonMode)}
      >
        <TabsList className="h-9">
          <TabsTrigger value="preset" className="px-2.5 text-xs">
            {t('comparison.modePreset')}
          </TabsTrigger>
          <TabsTrigger value="custom" className="px-2.5 text-xs">
            {t('comparison.modeCustom')}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {comparisonMode === 'preset' ? (
        <Select value={comparisonPreset} onValueChange={(value) => setComparisonPreset(value as ComparisonPreset)}>
          <SelectTrigger className="h-9 w-[140px] text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRESET_OPTIONS.map((preset) => (
              <SelectItem key={preset.value} value={preset.value}>
                {t(preset.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <>
          <ComparisonDateRangeButton
            label={t('comparison.period1')}
            start={comparisonPeriod1Start}
            end={comparisonPeriod1End}
            onChange={setComparisonPeriod1Range}
          />
          <ComparisonDateRangeButton
            label={t('comparison.period2')}
            start={comparisonPeriod2Start}
            end={comparisonPeriod2End}
            onChange={setComparisonPeriod2Range}
          />
        </>
      )}
    </div>
  )
}
