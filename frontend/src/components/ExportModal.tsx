import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { Download, Loader2, CalendarIcon, Building2, ChevronDown, FileSpreadsheet, Presentation, FileText } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Calendar } from '@/components/ui/calendar'
import { useToast } from '@/components/ui/use-toast'
import { accountsApi, exportsApi } from '@/services/api'
import { GoogleSheetsExportButton } from '@/components/GoogleSheetsExportButton'
import { downloadBlob } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { AmazonAccount } from '@/types'
import type { DateRange } from 'react-day-picker'

type ReportType = 'sales' | 'inventory' | 'advertising'
type DatePreset = '7' | '14' | '30' | '60' | '90' | '12m' | 'ytd' | 'lastyear' | 'custom'
type TemplateType = 'clean' | 'corporate' | 'executive'
type ExportFormat = 'excel' | 'powerpoint' | 'csv'

const FORMAT_OPTIONS: { id: ExportFormat; nameKey: string; descKey: string; icon: typeof FileSpreadsheet }[] = [
  { id: 'excel', nameKey: 'export.formatExcel', descKey: 'export.formatExcelDesc', icon: FileSpreadsheet },
  { id: 'powerpoint', nameKey: 'export.formatPowerpoint', descKey: 'export.formatPowerpointDesc', icon: Presentation },
  { id: 'csv', nameKey: 'export.formatCsv', descKey: 'export.formatCsvDesc', icon: FileText },
]

const PRESET_OPTIONS: { value: DatePreset; key: string }[] = [
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

const TEMPLATE_CONFIGS: {
  id: TemplateType
  nameKey: string
  descKey: string
  headerColor: string
  rowColors: [string, string]
  accentColor: string
}[] = [
  {
    id: 'clean',
    nameKey: 'export.templateClean',
    descKey: 'export.templateCleanDesc',
    headerColor: '#F0F0F0',
    rowColors: ['#FFFFFF', '#F9F9F9'],
    accentColor: '#333333',
  },
  {
    id: 'corporate',
    nameKey: 'export.templateCorporate',
    descKey: 'export.templateCorporateDesc',
    headerColor: '#1F4E79',
    rowColors: ['#FFFFFF', '#D6E4F0'],
    accentColor: '#1F4E79',
  },
  {
    id: 'executive',
    nameKey: 'export.templateExecutive',
    descKey: 'export.templateExecutiveDesc',
    headerColor: '#1B2631',
    rowColors: ['#FFFFFF', '#EAECEE'],
    accentColor: '#F39C12',
  },
]

function TemplatePreview({
  config,
}: {
  config: (typeof TEMPLATE_CONFIGS)[number]
}) {
  const isLight = (hex: string) => {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return r * 0.299 + g * 0.587 + b * 0.114 > 150
  }
  const headerTextColor = isLight(config.headerColor) ? '#333333' : '#FFFFFF'

  return (
    <div className="w-full rounded overflow-hidden border border-border/50">
      {/* Header bar */}
      <div
        className="h-5 flex items-center px-1.5 gap-1"
        style={{ backgroundColor: config.headerColor }}
      >
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-2 rounded-sm flex-1"
            style={{
              backgroundColor: headerTextColor,
              opacity: 0.6,
            }}
          />
        ))}
      </div>
      {/* Data rows */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="h-3.5 flex items-center px-1.5 gap-1"
          style={{ backgroundColor: config.rowColors[i % 2] }}
        >
          {[1, 2, 3].map((j) => (
            <div
              key={j}
              className="h-1.5 rounded-sm flex-1"
              style={{
                backgroundColor: j === 1 && i === 0 ? config.accentColor : '#CBD5E1',
                opacity: j === 1 && i === 0 ? 0.7 : 0.35,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

function computeDateRange(preset: DatePreset, customStart: string | null, customEnd: string | null) {
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

  if (preset === 'custom' && customStart && customEnd) {
    return { start: customStart, end: customEnd }
  }

  const today = new Date()
  if (preset === '12m') {
    const targetYear = today.getFullYear() - 1
    const targetMonth = today.getMonth()
    const lastDayOfMonth = new Date(targetYear, targetMonth + 1, 0).getDate()
    const start = new Date(targetYear, targetMonth, Math.min(today.getDate(), lastDayOfMonth))
    return { start: fmt(start), end: fmt(today) }
  }
  if (preset === 'ytd') {
    return { start: fmt(new Date(today.getFullYear(), 0, 1)), end: fmt(today) }
  }
  if (preset === 'lastyear') {
    return {
      start: fmt(new Date(today.getFullYear() - 1, 0, 1)),
      end: fmt(new Date(today.getFullYear() - 1, 11, 31)),
    }
  }

  const days = parseInt(preset) || 30
  const end = new Date()
  const start = new Date()
  start.setDate(start.getDate() - days)
  return { start: fmt(start), end: fmt(end) }
}

interface ExportModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ExportModal({ open, onOpenChange }: ExportModalProps) {
  const { t, language: uiLanguage } = useTranslation()
  const { toast } = useToast()

  // Local state (independent from page filters)
  const [reportTypes, setReportTypes] = useState<Set<ReportType>>(new Set(['sales', 'inventory']))
  // Export language defaults to the UI language so client documents come out
  // in the language the user is already working in.
  const [language, setLanguage] = useState<'en' | 'it'>(uiLanguage)
  const [exportFormat, setExportFormat] = useState<ExportFormat>('excel')
  const [datePreset, setDatePreset] = useState<DatePreset>('12m')
  const [customStartDate, setCustomStartDate] = useState<string | null>(null)
  const [customEndDate, setCustomEndDate] = useState<string | null>(null)
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateType>('corporate')
  const [isExporting, setIsExporting] = useState(false)
  const [calendarOpen, setCalendarOpen] = useState(false)
  const [accountsOpen, setAccountsOpen] = useState(false)

  const { data: accounts } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
    enabled: open,
  })

  // Keep the export language aligned with the UI language each time the modal opens.
  useEffect(() => {
    if (open) setLanguage(uiLanguage)
  }, [open, uiLanguage])

  const toggleReportType = (type: ReportType) => {
    setReportTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }

  const toggleAccountId = (id: string) => {
    setSelectedAccountIds((prev) =>
      prev.includes(id) ? prev.filter((a) => a !== id) : [...prev, id]
    )
  }

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
      setCustomStartDate(format(range.from, 'yyyy-MM-dd'))
      setCustomEndDate(format(range.to, 'yyyy-MM-dd'))
      setCalendarOpen(false)
    }
  }

  const handleExport = async () => {
    if (reportTypes.size === 0) return
    setIsExporting(true)
    try {
      const dateRange = computeDateRange(datePreset, customStartDate, customEndDate)
      const accountIds = selectedAccountIds.length > 0 ? selectedAccountIds : undefined
      const types = Array.from(reportTypes)

      if (exportFormat === 'powerpoint') {
        const blob = await exportsApi.exportPowerPoint({
          start_date: dateRange.start,
          end_date: dateRange.end,
          account_ids: accountIds,
          language,
        })
        downloadBlob(blob, `inthezon_presentation_${dateRange.start}_${dateRange.end}_${language}.pptx`)
      } else if (exportFormat === 'csv') {
        const blob = await exportsApi.exportBundle({
          report_types: types,
          start_date: dateRange.start,
          end_date: dateRange.end,
          account_ids: accountIds,
          group_by: reportTypes.has('sales') ? 'day' : undefined,
          low_stock_only: reportTypes.has('inventory') ? false : undefined,
          language,
          include_comparison: true,
        })
        downloadBlob(blob, `inthezon_export_${dateRange.start}_${dateRange.end}_${language}.zip`)
      } else {
        const blob = await exportsApi.exportExcelBundle({
          report_types: types,
          start_date: dateRange.start,
          end_date: dateRange.end,
          account_ids: accountIds,
          group_by: reportTypes.has('sales') ? 'day' : undefined,
          low_stock_only: reportTypes.has('inventory') ? false : undefined,
          language,
          include_comparison: true,
          template: selectedTemplate,
        })
        downloadBlob(blob, `inthezon_export_${dateRange.start}_${dateRange.end}_${language}_${selectedTemplate}.xlsx`)
      }

      toast({ title: t('export.success') })
      onOpenChange(false)
    } catch {
      toast({
        variant: 'destructive',
        title: t('reports.exportFailed'),
        description: t('reports.exportFailedDesc'),
      })
    } finally {
      setIsExporting(false)
    }
  }

  const selectedAccountCount = selectedAccountIds.length
  const accountLabel =
    selectedAccountCount === 0
      ? t('export.allAccounts')
      : selectedAccountCount === 1
        ? accounts?.find((a) => a.id === selectedAccountIds[0])?.account_name || '1 account'
        : t('filter.nAccounts', { n: selectedAccountCount })

  const dateDisplayLabel =
    datePreset === 'custom' && customStartDate && customEndDate
      ? `${format(new Date(customStartDate + 'T00:00:00'), 'MMM d')} - ${format(new Date(customEndDate + 'T00:00:00'), 'MMM d')}`
      : undefined
  const dateRange = computeDateRange(datePreset, customStartDate, customEndDate)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>{t('export.title')}</DialogTitle>
          <DialogDescription>{t('export.subtitle')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          {/* Report Types */}
          <div className="space-y-2">
            <label className="text-sm font-medium">{t('export.reportTypes')}</label>
            <div className="flex gap-4">
              {(['sales', 'inventory', 'advertising'] as ReportType[]).map((type) => (
                <label key={type} className="flex items-center gap-2 cursor-pointer">
                  <Checkbox
                    checked={reportTypes.has(type)}
                    onCheckedChange={() => toggleReportType(type)}
                  />
                  <span className="text-sm">{t(`reports.${type}`)}</span>
                </label>
              ))}
            </div>
            {reportTypes.size === 0 && (
              <p className="text-xs text-destructive">{t('export.selectAtLeastOne')}</p>
            )}
          </div>

          {/* Format Selection */}
          <div className="space-y-2">
            <label className="text-sm font-medium">{t('export.format')}</label>
            <div className="grid grid-cols-3 gap-3">
              {FORMAT_OPTIONS.map((fmt) => {
                const Icon = fmt.icon
                return (
                  <button
                    key={fmt.id}
                    type="button"
                    onClick={() => setExportFormat(fmt.id)}
                    className={`rounded-lg border-2 p-2.5 text-left transition-all hover:shadow-sm ${
                      exportFormat === fmt.id
                        ? 'border-primary bg-primary/5 shadow-sm'
                        : 'border-border hover:border-border/80'
                    }`}
                  >
                    <Icon className="h-5 w-5 text-primary" />
                    <p className="text-xs font-medium mt-2">{t(fmt.nameKey)}</p>
                    <p className="text-[10px] text-muted-foreground leading-tight mt-0.5">
                      {t(fmt.descKey)}
                    </p>
                  </button>
                )
              })}
            </div>
          </div>

          {/* Template Selection (Excel only) */}
          {exportFormat === 'excel' && (
          <div className="space-y-2">
            <label className="text-sm font-medium">{t('export.template')}</label>
            <div className="grid grid-cols-3 gap-3">
              {TEMPLATE_CONFIGS.map((tmpl) => (
                <button
                  key={tmpl.id}
                  type="button"
                  onClick={() => setSelectedTemplate(tmpl.id)}
                  className={`rounded-lg border-2 p-2.5 text-left transition-all hover:shadow-sm ${
                    selectedTemplate === tmpl.id
                      ? 'border-primary bg-primary/5 shadow-sm'
                      : 'border-border hover:border-border/80'
                  }`}
                >
                  <TemplatePreview config={tmpl} />
                  <div className="mt-2">
                    <p className="text-xs font-medium">{t(tmpl.nameKey)}</p>
                    <p className="text-[10px] text-muted-foreground leading-tight mt-0.5">
                      {t(tmpl.descKey)}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>
          )}

          {/* Language + Date Range */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('export.language')}</label>
              <Select value={language} onValueChange={(v) => setLanguage(v as 'en' | 'it')}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="it">Italiano</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">{t('export.dateRange')}</label>
              <Select value={datePreset} onValueChange={handlePresetChange}>
                <SelectTrigger className="h-9 text-sm">
                  <CalendarIcon className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
                  <SelectValue>
                    {dateDisplayLabel || t(PRESET_OPTIONS.find((p) => p.value === datePreset)?.key || '')}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {PRESET_OPTIONS.map((preset) => (
                    <SelectItem key={preset.value} value={preset.value}>
                      {t(preset.key)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Custom date calendar */}
          {datePreset === 'custom' && (
            <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="w-full h-9 text-xs">
                  {customStartDate && customEndDate
                    ? `${format(new Date(customStartDate + 'T00:00:00'), 'MMM d, yyyy')} - ${format(new Date(customEndDate + 'T00:00:00'), 'MMM d, yyyy')}`
                    : t('filter.pickDates')}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="range"
                  selected={{
                    from: customStartDate ? new Date(customStartDate + 'T00:00:00') : undefined,
                    to: customEndDate ? new Date(customEndDate + 'T00:00:00') : undefined,
                  }}
                  onSelect={handleDateSelect}
                  numberOfMonths={2}
                  disabled={{ after: new Date() }}
                />
              </PopoverContent>
            </Popover>
          )}

          {/* Accounts */}
          <div className="space-y-2">
            <label className="text-sm font-medium">{t('export.accounts')}</label>
            <Popover open={accountsOpen} onOpenChange={setAccountsOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" className="w-full h-9 justify-between text-sm font-normal">
                  <span className="flex items-center gap-2">
                    <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                    {accountLabel}
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-3" align="start">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{t('filter.accounts')}</span>
                    {selectedAccountCount > 0 && (
                      <button
                        className="text-xs text-muted-foreground hover:text-foreground"
                        onClick={() => setSelectedAccountIds([])}
                      >
                        {t('common.clear')}
                      </button>
                    )}
                  </div>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {accounts?.map((account) => (
                      <label
                        key={account.id}
                        className="flex items-center gap-2 cursor-pointer rounded-sm px-1 py-1 hover:bg-accent"
                      >
                        <Checkbox
                          checked={selectedAccountIds.includes(account.id)}
                          onCheckedChange={() => toggleAccountId(account.id)}
                        />
                        <span className="text-sm flex-1 truncate">{account.account_name}</span>
                        <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                          {account.marketplace_country}
                        </Badge>
                      </label>
                    ))}
                    {(!accounts || accounts.length === 0) && (
                      <p className="text-xs text-muted-foreground py-2">{t('filter.noAccountsFound')}</p>
                    )}
                  </div>
                </div>
              </PopoverContent>
            </Popover>
          </div>
        </div>

        <DialogFooter>
          <GoogleSheetsExportButton
            dataTypes={Array.from(reportTypes)}
            startDate={dateRange.start}
            endDate={dateRange.end}
            accountIds={selectedAccountIds.length > 0 ? selectedAccountIds : undefined}
            language={language}
            groupBy={reportTypes.has('sales') ? 'day' : 'day'}
            disabled={reportTypes.size === 0 || isExporting}
            onSuccess={() => onOpenChange(false)}
          />
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleExport} disabled={reportTypes.size === 0 || isExporting}>
            {isExporting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('export.exporting')}
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                {t('export.download')}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
