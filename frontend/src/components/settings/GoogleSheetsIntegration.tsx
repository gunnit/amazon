import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import {
  ExternalLink,
  History,
  Link2,
  Loader2,
  Pencil,
  Play,
  Plus,
  Trash2,
} from 'lucide-react'

import { useAuthStore } from '@/store/authStore'
import { accountsApi, googleSheetsApi } from '@/services/api'
import type {
  AmazonAccount,
  GoogleSheetsConnection,
  GoogleSheetsDataType,
  GoogleSheetsFrequency,
  GoogleSheetsSync,
  GoogleSheetsSyncMode,
  GoogleSheetsSyncRun,
} from '@/types'
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
  weekday: number
  hour: number
  minute: number
}

type FormState = {
  name: string
  data_types: GoogleSheetsDataType[]
  frequency: GoogleSheetsFrequency
  sync_mode: GoogleSheetsSyncMode
  timezone: string
  account_ids: string[]
  parameters: {
    language: 'en' | 'it'
    group_by: 'day' | 'week' | 'month'
    date_range_days: number
  }
  schedule_config: ScheduleConfig
}

const DEFAULT_FORM_PARAMETERS: FormState['parameters'] = {
  language: 'en',
  group_by: 'day',
  date_range_days: 7,
}

const WEEKDAY_VALUES = [
  { value: '0', key: 'googleSheets.monday' },
  { value: '1', key: 'googleSheets.tuesday' },
  { value: '2', key: 'googleSheets.wednesday' },
  { value: '3', key: 'googleSheets.thursday' },
  { value: '4', key: 'googleSheets.friday' },
  { value: '5', key: 'googleSheets.saturday' },
  { value: '6', key: 'googleSheets.sunday' },
]

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
  if (status === 'completed') return 'default'
  if (status === 'failed') return 'destructive'
  return 'secondary'
}

function buildDefaultForm(timezone: string): FormState {
  return {
    name: '',
    data_types: ['sales', 'inventory'],
    frequency: 'daily',
    sync_mode: 'overwrite',
    timezone,
    account_ids: [],
    parameters: { ...DEFAULT_FORM_PARAMETERS },
    schedule_config: { weekday: 0, hour: 9, minute: 0 },
  }
}

function buildFormFromSync(sync: GoogleSheetsSync): FormState {
  const parameters = sync.parameters || {}
  const scheduleConfig = sync.schedule_config || {}
  return {
    name: sync.name,
    data_types: sync.data_types,
    frequency: sync.frequency,
    sync_mode: sync.sync_mode,
    timezone: sync.timezone,
    account_ids: sync.account_ids,
    parameters: {
      language: parameters.language === 'it' ? 'it' : 'en',
      group_by:
        parameters.group_by === 'week' || parameters.group_by === 'month'
          ? parameters.group_by
          : 'day',
      date_range_days:
        typeof parameters.date_range_days === 'number' && parameters.date_range_days > 0
          ? parameters.date_range_days
          : sync.frequency === 'daily'
            ? 1
            : 7,
    },
    schedule_config: {
      weekday: typeof scheduleConfig.weekday === 'number' ? scheduleConfig.weekday : 0,
      hour: typeof scheduleConfig.hour === 'number' ? scheduleConfig.hour : 9,
      minute: typeof scheduleConfig.minute === 'number' ? scheduleConfig.minute : 0,
    },
  }
}

export function GoogleSheetsIntegration() {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const organization = useAuthStore((state) => state.organization)
  const defaultTimezone = organization?.timezone || 'UTC'

  const [dialogOpen, setDialogOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [editingSync, setEditingSync] = useState<GoogleSheetsSync | null>(null)
  const [historySync, setHistorySync] = useState<GoogleSheetsSync | null>(null)
  const [formState, setFormState] = useState<FormState>(() => buildDefaultForm(defaultTimezone))

  useEffect(() => {
    if (!dialogOpen) {
      setEditingSync(null)
      setFormState(buildDefaultForm(defaultTimezone))
    }
  }, [defaultTimezone, dialogOpen])

  const timezoneOptions = useMemo(() => getTimezoneOptions(defaultTimezone), [defaultTimezone])

  const { data: connection, isLoading: connectionLoading } = useQuery<GoogleSheetsConnection | null>({
    queryKey: ['google-connection'],
    queryFn: () => googleSheetsApi.getConnection(),
  })

  const { data: syncs = [], isLoading: syncsLoading } = useQuery<GoogleSheetsSync[]>({
    queryKey: ['google-syncs'],
    queryFn: () => googleSheetsApi.listSyncs(),
    enabled: Boolean(connection),
  })

  const { data: accounts = [] } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
  })

  const { data: runs = [], isLoading: runsLoading } = useQuery<GoogleSheetsSyncRun[]>({
    queryKey: ['google-sync-runs', historySync?.id],
    queryFn: () => googleSheetsApi.listSyncRuns(historySync!.id),
    enabled: historyOpen && !!historySync?.id,
  })

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['google-connection'] })
    await queryClient.invalidateQueries({ queryKey: ['google-syncs'] })
    await queryClient.invalidateQueries({ queryKey: ['google-sync-runs'] })
  }

  const connectMutation = useMutation({
    mutationFn: () => googleSheetsApi.getAuthUrl(),
    onSuccess: (authUrl) => {
      window.location.href = authUrl
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('googleSheets.connectFailed') })
    },
  })

  const disconnectMutation = useMutation({
    mutationFn: () => googleSheetsApi.disconnect(),
    onSuccess: async () => {
      await invalidate()
      toast({ title: t('googleSheets.disconnected') })
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('googleSheets.disconnectFailed') })
    },
  })

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        name: formState.name.trim(),
        data_types: formState.data_types,
        frequency: formState.frequency,
        sync_mode: formState.sync_mode,
        account_ids: formState.account_ids,
        parameters: formState.parameters,
        schedule_config:
          formState.frequency === 'weekly'
            ? {
                weekday: formState.schedule_config.weekday,
                hour: formState.schedule_config.hour,
                minute: formState.schedule_config.minute,
              }
            : {
                hour: formState.schedule_config.hour,
                minute: formState.schedule_config.minute,
              },
        timezone: formState.timezone,
      }

      if (editingSync) {
        return googleSheetsApi.updateSync(editingSync.id, payload)
      }
      return googleSheetsApi.createSync(payload)
    },
    onSuccess: async () => {
      await invalidate()
      setDialogOpen(false)
      toast({ title: t('googleSheets.saved') })
    },
    onError: (error) => {
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : null
      toast({
        variant: 'destructive',
        title: t('googleSheets.saveFailed'),
        ...(typeof detail === 'string' ? { description: detail } : {}),
      })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ syncId, enabled }: { syncId: string; enabled: boolean }) =>
      googleSheetsApi.toggleSync(syncId, enabled),
    onSuccess: invalidate,
    onError: () => toast({ variant: 'destructive', title: t('googleSheets.toggleFailed') }),
  })

  const runNowMutation = useMutation({
    mutationFn: (syncId: string) => googleSheetsApi.runSyncNow(syncId),
    onSuccess: async () => {
      await invalidate()
      toast({ title: t('googleSheets.runQueued') })
    },
    onError: () => toast({ variant: 'destructive', title: t('googleSheets.runFailed') }),
  })

  const deleteMutation = useMutation({
    mutationFn: (syncId: string) => googleSheetsApi.deleteSync(syncId),
    onSuccess: async () => {
      await invalidate()
      toast({ title: t('googleSheets.deleted') })
    },
    onError: () => toast({ variant: 'destructive', title: t('googleSheets.deleteFailed') }),
  })

  const openCreateDialog = () => {
    setEditingSync(null)
    setFormState(buildDefaultForm(defaultTimezone))
    setDialogOpen(true)
  }

  const openEditDialog = (sync: GoogleSheetsSync) => {
    setEditingSync(sync)
    setFormState(buildFormFromSync(sync))
    setDialogOpen(true)
  }

  const toggleDataType = (dataType: GoogleSheetsDataType) => {
    setFormState((current) => {
      const exists = current.data_types.includes(dataType)
      return {
        ...current,
        data_types: exists
          ? current.data_types.filter((value) => value !== dataType)
          : [...current.data_types, dataType],
      }
    })
  }

  const handleDisconnect = () => {
    if (!window.confirm(t('googleSheets.disconnectConfirm'))) return
    disconnectMutation.mutate()
  }

  const handleDelete = (sync: GoogleSheetsSync) => {
    if (!window.confirm(t('googleSheets.deleteConfirm', { name: sync.name }))) return
    deleteMutation.mutate(sync.id)
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>{t('googleSheets.connectionTitle')}</CardTitle>
            <CardDescription>{t('googleSheets.connectionSubtitle')}</CardDescription>
          </div>
          {connection ? (
            <Button variant="outline" onClick={handleDisconnect} disabled={disconnectMutation.isPending}>
              {disconnectMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}
              {t('googleSheets.disconnect')}
            </Button>
          ) : (
            <Button onClick={() => connectMutation.mutate()} disabled={connectMutation.isPending}>
              {connectMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Link2 className="mr-2 h-4 w-4" />}
              {t('googleSheets.connect')}
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {connectionLoading ? (
            <div className="flex h-20 items-center justify-center">
              <Loader2 className="h-7 w-7 animate-spin text-primary" />
            </div>
          ) : connection ? (
            <div className="rounded-lg border p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge>{t('googleSheets.connected')}</Badge>
                <span className="font-medium">{connection.google_email}</span>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {t('googleSheets.connectedAt')}: {formatTimestamp(connection.connected_at)}
              </p>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              {t('googleSheets.notConnected')}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>{t('googleSheets.syncTitle')}</CardTitle>
            <CardDescription>{t('googleSheets.syncSubtitle')}</CardDescription>
          </div>
          <Button onClick={openCreateDialog} disabled={!connection}>
            <Plus className="mr-2 h-4 w-4" />
            {t('googleSheets.newSync')}
          </Button>
        </CardHeader>
        <CardContent>
          {!connection ? (
            <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              {t('googleSheets.connectBeforeSync')}
            </div>
          ) : syncsLoading ? (
            <div className="flex h-20 items-center justify-center">
              <Loader2 className="h-7 w-7 animate-spin text-primary" />
            </div>
          ) : syncs.length === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">
              {t('googleSheets.empty')}
            </div>
          ) : (
            <div className="space-y-3">
              {syncs.map((sync) => (
                <div key={sync.id} className="rounded-lg border p-4">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">{sync.name}</h3>
                        <Badge variant={toBadgeVariant(sync.last_run_status)}>
                          {sync.last_run_status || t('googleSheets.notRunYet')}
                        </Badge>
                        <Badge variant="secondary">{t(`googleSheets.${sync.frequency}`)}</Badge>
                        <Badge variant="secondary">{t(`googleSheets.${sync.sync_mode}`)}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {sync.data_types.map((value) => t(`googleSheets.dataType.${value}`)).join(', ')}
                      </p>
                      <div className="grid gap-1 text-sm text-muted-foreground sm:grid-cols-2">
                        <span>{t('googleSheets.nextRun')}: {formatTimestamp(sync.next_run_at)}</span>
                        <span>{t('googleSheets.lastRun')}: {formatTimestamp(sync.last_run_at)}</span>
                        <span>{t('googleSheets.timezone')}: {sync.timezone}</span>
                        <span>{t('googleSheets.accountsCount', { n: sync.account_ids.length || accounts.length })}</span>
                      </div>
                      {sync.spreadsheet_url ? (
                        <a
                          href={sync.spreadsheet_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-primary underline"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          {t('googleSheets.openSpreadsheet')}
                        </a>
                      ) : null}
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <div className="flex items-center gap-2 rounded-md border px-3 py-2">
                        <Switch
                          checked={sync.is_enabled}
                          onCheckedChange={(checked) =>
                            toggleMutation.mutate({ syncId: sync.id, enabled: checked })
                          }
                        />
                        <span className="text-sm">
                          {sync.is_enabled ? t('googleSheets.enabled') : t('googleSheets.disabled')}
                        </span>
                      </div>
                      <Button variant="outline" size="sm" onClick={() => runNowMutation.mutate(sync.id)}>
                        <Play className="mr-2 h-4 w-4" />
                        {t('googleSheets.runNow')}
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => openEditDialog(sync)}>
                        <Pencil className="mr-2 h-4 w-4" />
                        {t('common.edit')}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setHistorySync(sync)
                          setHistoryOpen(true)
                        }}
                      >
                        <History className="mr-2 h-4 w-4" />
                        {t('googleSheets.history')}
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleDelete(sync)}>
                        <Trash2 className="mr-2 h-4 w-4" />
                        {t('common.delete')}
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
              {editingSync ? t('googleSheets.editTitle') : t('googleSheets.createTitle')}
            </DialogTitle>
            <DialogDescription>{t('googleSheets.formSubtitle')}</DialogDescription>
          </DialogHeader>

          <div className="grid gap-5 py-1">
            <div className="grid gap-2">
              <Label htmlFor="google-sync-name">{t('googleSheets.name')}</Label>
              <Input
                id="google-sync-name"
                value={formState.name}
                onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
                placeholder={t('googleSheets.namePlaceholder')}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>{t('googleSheets.frequency')}</Label>
                <Select
                  value={formState.frequency}
                  onValueChange={(value: GoogleSheetsFrequency) =>
                    setFormState((current) => ({
                      ...current,
                      frequency: value,
                      parameters: {
                        ...current.parameters,
                        date_range_days: value === 'daily' ? 1 : Math.max(current.parameters.date_range_days, 7),
                      },
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">{t('googleSheets.daily')}</SelectItem>
                    <SelectItem value="weekly">{t('googleSheets.weekly')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="grid gap-2">
                <Label>{t('googleSheets.syncMode')}</Label>
                <Select
                  value={formState.sync_mode}
                  onValueChange={(value: GoogleSheetsSyncMode) =>
                    setFormState((current) => ({ ...current, sync_mode: value }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="overwrite">{t('googleSheets.overwrite')}</SelectItem>
                    <SelectItem value="append">{t('googleSheets.append')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid gap-2">
              <Label>{t('googleSheets.dataTypes')}</Label>
              <div className="grid gap-2 rounded-lg border p-3 sm:grid-cols-2">
                {(['sales', 'inventory', 'advertising', 'forecasts', 'analytics'] as GoogleSheetsDataType[]).map((dataType) => (
                  <label key={dataType} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={formState.data_types.includes(dataType)}
                      onCheckedChange={() => toggleDataType(dataType)}
                    />
                    <span>{t(`googleSheets.dataType.${dataType}`)}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {formState.frequency === 'weekly' ? (
                <div className="grid gap-2">
                  <Label>{t('googleSheets.weekday')}</Label>
                  <Select
                    value={String(formState.schedule_config.weekday)}
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
                  <Label>{t('googleSheets.dateRangeDays')}</Label>
                  <Input
                    type="number"
                    min={1}
                    max={90}
                    value={formState.parameters.date_range_days}
                    onChange={(event) =>
                      setFormState((current) => ({
                        ...current,
                        parameters: {
                          ...current.parameters,
                          date_range_days: Math.max(1, Math.min(90, Number(event.target.value) || 1)),
                        },
                      }))
                    }
                  />
                </div>
              )}

              <div className="grid gap-2">
                <Label>{t('googleSheets.time')}</Label>
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

            {formState.frequency === 'weekly' ? (
              <div className="grid gap-2">
                <Label>{t('googleSheets.dateRangeDays')}</Label>
                <Input
                  type="number"
                  min={1}
                  max={90}
                  value={formState.parameters.date_range_days}
                  onChange={(event) =>
                    setFormState((current) => ({
                      ...current,
                      parameters: {
                        ...current.parameters,
                        date_range_days: Math.max(1, Math.min(90, Number(event.target.value) || 7)),
                      },
                    }))
                  }
                />
                <p className="text-xs text-muted-foreground">{t('googleSheets.dateRangeHint')}</p>
              </div>
            ) : null}

            <div className="grid gap-2">
              <Label>{t('googleSheets.timezone')}</Label>
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
              <Label>{t('googleSheets.accounts')}</Label>
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
              <p className="text-xs text-muted-foreground">{t('googleSheets.accountsHint')}</p>
            </div>

            <div className="grid gap-3 rounded-lg border p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="grid gap-2">
                  <Label>{t('googleSheets.language')}</Label>
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
                  <Label>{t('googleSheets.groupBy')}</Label>
                  <Select
                    value={formState.parameters.group_by}
                    onValueChange={(value: 'day' | 'week' | 'month') =>
                      setFormState((current) => ({
                        ...current,
                        parameters: { ...current.parameters, group_by: value },
                      }))
                    }
                    disabled={!formState.data_types.includes('sales')}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="day">{t('googleSheets.groupByDay')}</SelectItem>
                      <SelectItem value="week">{t('googleSheets.groupByWeek')}</SelectItem>
                      <SelectItem value="month">{t('googleSheets.groupByMonth')}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || !formState.name.trim() || formState.data_types.length === 0}
            >
              {saveMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {editingSync ? t('common.save') : t('googleSheets.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[760px]">
          <DialogHeader>
            <DialogTitle>{historySync?.name}</DialogTitle>
            <DialogDescription>{t('googleSheets.historySubtitle')}</DialogDescription>
          </DialogHeader>
          {runsLoading ? (
            <div className="flex h-24 items-center justify-center">
              <Loader2 className="h-7 w-7 animate-spin text-primary" />
            </div>
          ) : runs.length === 0 ? (
            <div className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">
              {t('googleSheets.noHistory')}
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
                        {t('googleSheets.rowsWritten')}: {run.rows_written ?? 0}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {run.data_types_snapshot.map((value) => t(`googleSheets.dataType.${value}`)).join(', ')}
                      </p>
                      {run.error_message ? (
                        <p className="text-sm text-destructive">{run.error_message}</p>
                      ) : (
                        <p className="text-sm text-muted-foreground">{run.progress_step || '—'}</p>
                      )}
                    </div>
                    {run.spreadsheet_url ? (
                      <a
                        href={run.spreadsheet_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-2 text-sm text-primary underline"
                      >
                        <ExternalLink className="h-4 w-4" />
                        {t('googleSheets.openSpreadsheet')}
                      </a>
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
