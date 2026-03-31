import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { Download, History, Loader2, Mail, Pencil, Play, Plus } from 'lucide-react'

import { useAuthStore } from '@/store/authStore'
import { accountsApi, reportsApi } from '@/services/api'
import type {
  AmazonAccount,
  ScheduledReport,
  ScheduledReportFormat,
  ScheduledReportFrequency,
  ScheduledReportParameters,
  ScheduledReportRun,
  ScheduledReportType,
} from '@/types'
import { downloadBlob, formatDate } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import { useToast } from '@/components/ui/use-toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

type ScheduleConfig = {
  weekday?: number
  day_of_month?: number
  hour: number
  minute: number
}

type FormState = {
  name: string
  report_types: ScheduledReportType[]
  frequency: ScheduledReportFrequency
  format: ScheduledReportFormat
  timezone: string
  account_ids: string[]
  recipientsText: string
  parameters: ScheduledReportParameters
  schedule_config: ScheduleConfig
  is_enabled: boolean
}

const DEFAULT_PARAMETERS: ScheduledReportParameters = {
  group_by: 'day',
  low_stock_only: false,
  language: 'en',
  include_comparison: true,
}

const WEEKDAY_VALUES = [
  { value: '0', key: 'scheduledReports.monday' },
  { value: '1', key: 'scheduledReports.tuesday' },
  { value: '2', key: 'scheduledReports.wednesday' },
  { value: '3', key: 'scheduledReports.thursday' },
  { value: '4', key: 'scheduledReports.friday' },
  { value: '5', key: 'scheduledReports.saturday' },
  { value: '6', key: 'scheduledReports.sunday' },
]

function buildDefaultForm(timezone: string): FormState {
  return {
    name: '',
    report_types: ['sales', 'inventory'],
    frequency: 'weekly',
    format: 'excel',
    timezone,
    account_ids: [],
    recipientsText: '',
    parameters: { ...DEFAULT_PARAMETERS },
    schedule_config: { weekday: 0, day_of_month: 1, hour: 9, minute: 0 },
    is_enabled: true,
  }
}

function buildFormFromSchedule(schedule: ScheduledReport): FormState {
  const config = schedule.schedule_config || {}
  return {
    name: schedule.name,
    report_types: schedule.report_types,
    frequency: schedule.frequency,
    format: schedule.format,
    timezone: schedule.timezone,
    account_ids: schedule.account_ids,
    recipientsText: schedule.recipients.join(', '),
    parameters: { ...DEFAULT_PARAMETERS, ...schedule.parameters },
    schedule_config: {
      weekday: typeof config.weekday === 'number' ? config.weekday : 0,
      day_of_month: typeof config.day_of_month === 'number' ? config.day_of_month : 1,
      hour: typeof config.hour === 'number' ? config.hour : 9,
      minute: typeof config.minute === 'number' ? config.minute : 0,
    },
    is_enabled: schedule.is_enabled,
  }
}

function parseRecipients(text: string) {
  return text
    .split(',')
    .map((email) => email.trim())
    .filter(Boolean)
}

function getTimezoneOptions(currentTimezone: string) {
  const fallback = ['UTC', 'Europe/Rome', 'Europe/London', 'America/New_York', 'America/Los_Angeles']
  const intlWithSupportedValuesOf = Intl as unknown as {
    supportedValuesOf?: (key: string) => string[]
  }
  const supported =
    typeof Intl !== 'undefined' && 'supportedValuesOf' in Intl
      ? intlWithSupportedValuesOf.supportedValuesOf?.('timeZone') || fallback
      : fallback
  return Array.from(new Set([currentTimezone, ...supported])).slice(0, 200)
}

function formatTimestamp(value: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function toBadgeVariant(status: string | null): 'default' | 'secondary' | 'destructive' {
  if (status === 'delivered') return 'default'
  if (status === 'failed') return 'destructive'
  return 'secondary'
}

export function ScheduledReportsPanel() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const organization = useAuthStore((state) => state.organization)
  const defaultTimezone = organization?.timezone || 'UTC'

  const [dialogOpen, setDialogOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState<ScheduledReport | null>(null)
  const [historySchedule, setHistorySchedule] = useState<ScheduledReport | null>(null)
  const [formState, setFormState] = useState<FormState>(() => buildDefaultForm(defaultTimezone))

  useEffect(() => {
    if (!dialogOpen) {
      setEditingSchedule(null)
      setFormState(buildDefaultForm(defaultTimezone))
    }
  }, [dialogOpen, defaultTimezone])

  const timezoneOptions = useMemo(() => getTimezoneOptions(defaultTimezone), [defaultTimezone])

  const { data: schedules = [], isLoading } = useQuery<ScheduledReport[]>({
    queryKey: ['scheduled-reports'],
    queryFn: () => reportsApi.listSchedules(),
  })

  const { data: accounts = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: runs = [], isLoading: runsLoading } = useQuery<ScheduledReportRun[]>({
    queryKey: ['scheduled-report-runs', historySchedule?.id],
    queryFn: () => reportsApi.listScheduleRuns(historySchedule!.id),
    enabled: historyOpen && !!historySchedule?.id,
  })

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['scheduled-reports'] })
    await queryClient.invalidateQueries({ queryKey: ['scheduled-report-runs'] })
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const recipients = parseRecipients(formState.recipientsText)
      const payload = {
        name: formState.name.trim(),
        report_types: formState.report_types,
        frequency: formState.frequency,
        format: formState.format,
        timezone: formState.timezone,
        account_ids: formState.account_ids,
        recipients,
        parameters: formState.parameters,
        schedule_config:
          formState.frequency === 'weekly'
            ? {
                weekday: formState.schedule_config.weekday ?? 0,
                hour: formState.schedule_config.hour,
                minute: formState.schedule_config.minute,
              }
            : {
                day_of_month: formState.schedule_config.day_of_month ?? 1,
                hour: formState.schedule_config.hour,
                minute: formState.schedule_config.minute,
              },
        is_enabled: formState.is_enabled,
      }
      if (editingSchedule) {
        return reportsApi.updateSchedule(editingSchedule.id, payload)
      }
      return reportsApi.createSchedule(payload)
    },
    onSuccess: async () => {
      await invalidate()
      setDialogOpen(false)
      toast({ title: t('scheduledReports.saved') })
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null
      toast({
        variant: 'destructive',
        title: t('scheduledReports.saveFailed'),
        description: typeof detail === 'string' ? detail : t('scheduledReports.saveFailedDesc'),
      })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ scheduleId, enabled }: { scheduleId: string; enabled: boolean }) =>
      reportsApi.toggleSchedule(scheduleId, enabled),
    onSuccess: invalidate,
    onError: () => toast({ variant: 'destructive', title: t('scheduledReports.toggleFailed') }),
  })

  const runNowMutation = useMutation({
    mutationFn: (scheduleId: string) => reportsApi.runScheduleNow(scheduleId),
    onSuccess: async () => {
      await invalidate()
      toast({ title: t('scheduledReports.runQueued') })
    },
    onError: () => toast({ variant: 'destructive', title: t('scheduledReports.runFailed') }),
  })

  const downloadMutation = useMutation({
    mutationFn: async (run: ScheduledReportRun) => {
      const blob = await reportsApi.downloadScheduleRun(run.id)
      return { blob, filename: run.artifact_filename || `scheduled-report-${run.id}` }
    },
    onSuccess: ({ blob, filename }) => downloadBlob(blob, filename),
    onError: () => toast({ variant: 'destructive', title: t('scheduledReports.downloadFailed') }),
  })

  const openCreateDialog = () => {
    setEditingSchedule(null)
    setFormState(buildDefaultForm(defaultTimezone))
    setDialogOpen(true)
  }

  const openEditDialog = (schedule: ScheduledReport) => {
    setEditingSchedule(schedule)
    setFormState(buildFormFromSchedule(schedule))
    setDialogOpen(true)
  }

  const toggleReportType = (reportType: ScheduledReportType) => {
    setFormState((current) => {
      const exists = current.report_types.includes(reportType)
      return {
        ...current,
        report_types: exists
          ? current.report_types.filter((value) => value !== reportType)
          : [...current.report_types, reportType],
      }
    })
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>{t('scheduledReports.title')}</CardTitle>
            <CardDescription>{t('scheduledReports.subtitle')}</CardDescription>
          </div>
          <Button onClick={openCreateDialog}>
            <Plus className="mr-2 h-4 w-4" />
            {t('scheduledReports.new')}
          </Button>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-28 items-center justify-center">
              <Loader2 className="h-7 w-7 animate-spin text-primary" />
            </div>
          ) : schedules.length === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              {t('scheduledReports.empty')}
            </div>
          ) : (
            <div className="space-y-3">
              {schedules.map((schedule) => (
                <div key={schedule.id} className="rounded-lg border p-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">{schedule.name}</h3>
                        <Badge variant={toBadgeVariant(schedule.last_run_status)}>
                          {schedule.last_run_status || t('scheduledReports.notRunYet')}
                        </Badge>
                        <Badge variant="secondary">{schedule.format.toUpperCase()}</Badge>
                        <Badge variant="secondary">{t(`scheduledReports.${schedule.frequency}`)}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {schedule.report_types.join(', ')} · {schedule.recipients.length} {t('scheduledReports.recipients')}
                      </p>
                      <div className="grid gap-1 text-sm text-muted-foreground sm:grid-cols-2">
                        <span>{t('scheduledReports.nextRun')}: {formatTimestamp(schedule.next_run_at)}</span>
                        <span>{t('scheduledReports.lastRun')}: {formatTimestamp(schedule.last_run_at)}</span>
                        <span>{t('scheduledReports.timezone')}: {schedule.timezone}</span>
                        <span>{t('scheduledReports.accountsCount', { n: schedule.account_ids.length || accounts.length })}</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                        <Switch
                          checked={schedule.is_enabled}
                          onCheckedChange={(checked) =>
                            toggleMutation.mutate({ scheduleId: schedule.id, enabled: checked })
                          }
                        />
                        <span className="text-sm">
                          {schedule.is_enabled ? t('scheduledReports.enabled') : t('scheduledReports.disabled')}
                        </span>
                      </div>
                      <Button variant="outline" size="sm" onClick={() => runNowMutation.mutate(schedule.id)}>
                        <Play className="mr-2 h-4 w-4" />
                        {t('scheduledReports.runNow')}
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => openEditDialog(schedule)}>
                        <Pencil className="mr-2 h-4 w-4" />
                        {t('common.edit')}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setHistorySchedule(schedule)
                          setHistoryOpen(true)
                        }}
                      >
                        <History className="mr-2 h-4 w-4" />
                        {t('scheduledReports.history')}
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[760px]">
          <DialogHeader>
            <DialogTitle>
              {editingSchedule ? t('scheduledReports.editTitle') : t('scheduledReports.createTitle')}
            </DialogTitle>
            <DialogDescription>{t('scheduledReports.formSubtitle')}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-5 py-1">
            <div className="grid gap-2">
              <Label htmlFor="scheduled-report-name">{t('scheduledReports.name')}</Label>
              <Input
                id="scheduled-report-name"
                value={formState.name}
                onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
                placeholder={t('scheduledReports.namePlaceholder')}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>{t('scheduledReports.frequency')}</Label>
                <Select
                  value={formState.frequency}
                  onValueChange={(value: ScheduledReportFrequency) =>
                    setFormState((current) => ({ ...current, frequency: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="weekly">{t('scheduledReports.weekly')}</SelectItem>
                    <SelectItem value="monthly">{t('scheduledReports.monthly')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>{t('scheduledReports.format')}</Label>
                <Select
                  value={formState.format}
                  onValueChange={(value: ScheduledReportFormat) =>
                    setFormState((current) => ({ ...current, format: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="excel">Excel</SelectItem>
                    <SelectItem value="pdf">PDF</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid gap-2">
              <Label>{t('scheduledReports.reportTypes')}</Label>
              <div className="grid gap-2 rounded-lg border p-3 sm:grid-cols-3">
                {(['sales', 'inventory', 'advertising'] as ScheduledReportType[]).map((reportType) => (
                  <label key={reportType} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={formState.report_types.includes(reportType)}
                      onCheckedChange={() => toggleReportType(reportType)}
                    />
                    <span>{t(`reports.${reportType}`)}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {formState.frequency === 'weekly' ? (
                <div className="grid gap-2">
                  <Label>{t('scheduledReports.weekday')}</Label>
                  <Select
                    value={String(formState.schedule_config.weekday ?? 0)}
                    onValueChange={(value) =>
                      setFormState((current) => ({
                        ...current,
                        schedule_config: { ...current.schedule_config, weekday: Number(value) },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {WEEKDAY_VALUES.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {t(option.key)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              ) : (
                <div className="grid gap-2">
                  <Label>{t('scheduledReports.dayOfMonth')}</Label>
                  <Input
                    type="number"
                    min={1}
                    max={31}
                    value={formState.schedule_config.day_of_month ?? 1}
                    onChange={(event) =>
                      setFormState((current) => ({
                        ...current,
                        schedule_config: {
                          ...current.schedule_config,
                          day_of_month: Math.max(1, Math.min(31, Number(event.target.value) || 1)),
                        },
                      }))
                    }
                  />
                </div>
              )}

              <div className="grid gap-2">
                <Label>{t('scheduledReports.time')}</Label>
                <Input
                  type="time"
                  value={`${String(formState.schedule_config.hour).padStart(2, '0')}:${String(formState.schedule_config.minute).padStart(2, '0')}`}
                  onChange={(event) => {
                    const [hour, minute] = event.target.value.split(':').map((value) => Number(value))
                    setFormState((current) => ({
                      ...current,
                      schedule_config: { ...current.schedule_config, hour, minute },
                    }))
                  }}
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label>{t('scheduledReports.timezone')}</Label>
              <Select
                value={formState.timezone}
                onValueChange={(value) => setFormState((current) => ({ ...current, timezone: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {timezoneOptions.map((timezone) => (
                    <SelectItem key={timezone} value={timezone}>
                      {timezone}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid gap-2">
              <Label>{t('scheduledReports.accounts')}</Label>
              <div className="grid max-h-44 gap-2 overflow-y-auto rounded-lg border p-3 sm:grid-cols-2">
                {accounts.map((account) => (
                  <label key={account.id} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={formState.account_ids.includes(account.id)}
                      onCheckedChange={() =>
                        setFormState((current) => ({
                          ...current,
                          account_ids: current.account_ids.includes(account.id)
                            ? current.account_ids.filter((id) => id !== account.id)
                            : [...current.account_ids, account.id],
                        }))
                      }
                    />
                    <span>{account.account_name}</span>
                  </label>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{t('scheduledReports.accountsHint')}</p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="scheduled-report-recipients">{t('scheduledReports.recipientsLabel')}</Label>
              <Input
                id="scheduled-report-recipients"
                value={formState.recipientsText}
                onChange={(event) => setFormState((current) => ({ ...current, recipientsText: event.target.value }))}
                placeholder="alice@example.com, bob@example.com"
              />
            </div>

            <div className="grid gap-3 rounded-lg border p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="grid gap-2">
                  <Label>{t('scheduledReports.language')}</Label>
                  <Select
                    value={formState.parameters.language}
                    onValueChange={(value: 'en' | 'it') =>
                      setFormState((current) => ({
                        ...current,
                        parameters: { ...current.parameters, language: value },
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en">English</SelectItem>
                      <SelectItem value="it">Italiano</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid gap-2">
                  <Label>{t('scheduledReports.groupBy')}</Label>
                  <Select
                    value={formState.parameters.group_by}
                    onValueChange={(value: 'day' | 'week' | 'month') =>
                      setFormState((current) => ({
                        ...current,
                        parameters: { ...current.parameters, group_by: value },
                      }))
                    }
                    disabled={!formState.report_types.includes('sales')}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="day">{t('scheduledReports.groupByDay')}</SelectItem>
                      <SelectItem value="week">{t('scheduledReports.groupByWeek')}</SelectItem>
                      <SelectItem value="month">{t('scheduledReports.groupByMonth')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <label className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
                <div>
                  <div className="font-medium">{t('scheduledReports.includeComparison')}</div>
                  <div className="text-muted-foreground">{t('scheduledReports.includeComparisonDesc')}</div>
                </div>
                <Switch
                  checked={formState.parameters.include_comparison}
                  onCheckedChange={(checked) =>
                    setFormState((current) => ({
                      ...current,
                      parameters: { ...current.parameters, include_comparison: checked },
                    }))
                  }
                />
              </label>

              <label className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
                <div>
                  <div className="font-medium">{t('scheduledReports.lowStockOnly')}</div>
                  <div className="text-muted-foreground">{t('scheduledReports.lowStockOnlyDesc')}</div>
                </div>
                <Switch
                  checked={formState.parameters.low_stock_only}
                  disabled={!formState.report_types.includes('inventory')}
                  onCheckedChange={(checked) =>
                    setFormState((current) => ({
                      ...current,
                      parameters: { ...current.parameters, low_stock_only: checked },
                    }))
                  }
                />
              </label>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || !formState.name.trim() || formState.report_types.length === 0}
            >
              {saveMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {editingSchedule ? t('common.save') : t('scheduledReports.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[760px]">
          <DialogHeader>
            <DialogTitle>{historySchedule?.name}</DialogTitle>
            <DialogDescription>{t('scheduledReports.historySubtitle')}</DialogDescription>
          </DialogHeader>
          {runsLoading ? (
            <div className="flex h-24 items-center justify-center">
              <Loader2 className="h-7 w-7 animate-spin text-primary" />
            </div>
          ) : runs.length === 0 ? (
            <div className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
              {t('scheduledReports.noHistory')}
            </div>
          ) : (
            <div className="space-y-3">
              {runs.map((run) => (
                <div key={run.id} className="rounded-lg border p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={toBadgeVariant(run.status)}>{run.status}</Badge>
                        <span className="text-sm text-muted-foreground">{formatTimestamp(run.triggered_at)}</span>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {formatDate(run.period_start)} - {formatDate(run.period_end)}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        <Mail className="mr-1 inline h-4 w-4" />
                        {run.recipients.join(', ')}
                      </p>
                      {run.error_message ? (
                        <p className="text-sm text-destructive">{run.error_message}</p>
                      ) : (
                        <p className="text-sm text-muted-foreground">{run.progress_step || '—'}</p>
                      )}
                    </div>
                    {run.download_ready ? (
                      <Button variant="outline" size="sm" onClick={() => downloadMutation.mutate(run)}>
                        <Download className="mr-2 h-4 w-4" />
                        {t('scheduledReports.download')}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  )
}
