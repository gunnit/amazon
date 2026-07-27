import { useEffect, useState } from 'react'
import { format, subMonths } from 'date-fns'
import { ArrowRightLeft, CalendarRange, Play } from 'lucide-react'
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

const CALENDAR_FROM_YEAR = 2020

interface DraftRange {
  start: string
  end: string
}

function ComparisonDateRangeButton({
  label,
  range,
  onChange,
}: {
  label: string
  range: DraftRange | null
  onChange: (range: DraftRange) => void
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  // Track in-progress selection so the first click "sticks" before the user
  // picks the closing date. Without this, react-day-picker fires onSelect
  // with {from, to: undefined} on first click, which we'd ignore — leaving
  // the calendar visually frozen.
  const [pendingRange, setPendingRange] = useState<DateRange | undefined>(undefined)

  // Reset pending range whenever the popover closes or the committed range
  // changes from outside (e.g. reset button).
  useEffect(() => {
    if (!open) setPendingRange(undefined)
  }, [open])

  const committedRange: DateRange = {
    from: range ? new Date(range.start + 'T00:00:00') : undefined,
    to: range ? new Date(range.end + 'T00:00:00') : undefined,
  }
  const displayedRange: DateRange = pendingRange ?? committedRange

  const handleSelect = (selected: DateRange | undefined) => {
    setPendingRange(selected)
    if (selected?.from && selected?.to) {
      onChange({ start: format(selected.from, 'yyyy-MM-dd'), end: format(selected.to, 'yyyy-MM-dd') })
      setOpen(false)
      setPendingRange(undefined)
    }
  }

  const defaultMonth = displayedRange.from ?? subMonths(new Date(), 1)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 min-w-[185px] justify-start text-xs">
          <CalendarRange className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
          {range
            ? `${label}: ${format(new Date(range.start + 'T00:00:00'), 'MMM d, yyyy')} - ${format(new Date(range.end + 'T00:00:00'), 'MMM d, yyyy')}`
            : `${label}: ${t('filter.pickDates')}`}
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
          selected={displayedRange}
          onSelect={handleSelect}
          numberOfMonths={2}
          defaultMonth={defaultMonth}
          disabled={{ after: new Date() }}
          captionLayout="dropdown-buttons"
          fromYear={CALENDAR_FROM_YEAR}
          toYear={new Date().getFullYear()}
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

  // Picked dates live here as a draft; nothing fires until the user presses
  // Apply. Before this, the comparison silently kept showing preset data
  // until both ranges happened to be complete, with no cue that the input
  // hadn't been submitted.
  const [draft1, setDraft1] = useState<DraftRange | null>(
    comparisonPeriod1Start && comparisonPeriod1End
      ? { start: comparisonPeriod1Start, end: comparisonPeriod1End }
      : null
  )
  const [draft2, setDraft2] = useState<DraftRange | null>(
    comparisonPeriod2Start && comparisonPeriod2End
      ? { start: comparisonPeriod2Start, end: comparisonPeriod2End }
      : null
  )

  // Follow external store changes (e.g. the reset button).
  useEffect(() => {
    setDraft1(
      comparisonPeriod1Start && comparisonPeriod1End
        ? { start: comparisonPeriod1Start, end: comparisonPeriod1End }
        : null
    )
    setDraft2(
      comparisonPeriod2Start && comparisonPeriod2End
        ? { start: comparisonPeriod2Start, end: comparisonPeriod2End }
        : null
    )
  }, [comparisonPeriod1Start, comparisonPeriod1End, comparisonPeriod2Start, comparisonPeriod2End])

  const complete = Boolean(draft1 && draft2)
  const applied =
    complete &&
    draft1!.start === comparisonPeriod1Start &&
    draft1!.end === comparisonPeriod1End &&
    draft2!.start === comparisonPeriod2Start &&
    draft2!.end === comparisonPeriod2End

  const handleApply = () => {
    if (!draft1 || !draft2) return
    setComparisonPeriod1Range(draft1.start, draft1.end)
    setComparisonPeriod2Range(draft2.start, draft2.end)
  }

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
            range={draft1}
            onChange={setDraft1}
          />
          <ComparisonDateRangeButton
            label={t('comparison.period2')}
            range={draft2}
            onChange={setDraft2}
          />
          <Button
            size="sm"
            className="h-9 text-xs"
            disabled={!complete || applied}
            onClick={handleApply}
          >
            <Play className="mr-1.5 h-3.5 w-3.5" />
            {t('comparison.apply')}
          </Button>
          {!complete && (
            <span className="text-xs text-muted-foreground">{t('comparison.applyHint')}</span>
          )}
        </>
      )}
    </div>
  )
}
