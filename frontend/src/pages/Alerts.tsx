import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  BellRing,
  Bell,
  Plus,
  Trash2,
  Pencil,
  Loader2,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  Clock,
  FilterX,
  Mail,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useToast } from '@/components/ui/use-toast'
import { alertsApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import { cn, formatDate, formatNumber } from '@/lib/utils'
import {
  optimisticallyMarkAlertRead,
  optimisticallyMarkAllAlertsRead,
  restoreAlertQuerySnapshot,
} from '@/lib/alertUtils'
import type { AlertRule, AlertType } from '@/types'

const ALERT_TYPES: AlertType[] = ['low_stock', 'sync_failure', 'price_change', 'bsr_drop']

function severityIcon(severity: string) {
  switch (severity) {
    case 'critical':
      return <AlertCircle className="h-4 w-4 text-red-500" />
    case 'warning':
      return <AlertTriangle className="h-4 w-4 text-amber-500" />
    default:
      return <Info className="h-4 w-4 text-blue-500" />
  }
}

function severityBadge(severity: string) {
  const variant = severity === 'critical' ? 'destructive' : severity === 'warning' ? 'outline' : 'secondary'
  return <Badge variant={variant}>{severity}</Badge>
}

function alertTypeBadge(type: string | null, t: (key: string) => string) {
  const labels: Record<string, string> = {
    low_stock: t('alerts.type.low_stock'),
    sync_failure: t('alerts.type.sync_failure'),
    price_change: t('alerts.type.price_change'),
    bsr_drop: t('alerts.type.bsr_drop'),
    product_trend: t('alerts.type.product_trend'),
  }

  return <Badge variant="secondary">{type ? labels[type] || type : '—'}</Badge>
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function syncConditionValue(
  conditions: Record<string, unknown> | undefined,
  key: string,
  fallback: number,
  legacyKey?: string,
): string {
  const value = conditions?.[key]
  const legacyValue = legacyKey ? conditions?.[legacyKey] : undefined
  const resolved = typeof value === 'number' ? value : typeof legacyValue === 'number' ? legacyValue : fallback
  return String(resolved)
}

function syncRuleSummary(conditions: Record<string, unknown> | undefined, t: (key: string) => string) {
  const staleHours = syncConditionValue(conditions, 'stale_after_hours', 24, 'stale_hours')
  const graceMinutes = syncConditionValue(conditions, 'grace_period_minutes', 90)
  const stuckMinutes = syncConditionValue(conditions, 'stuck_after_minutes', 120)
  return `${t('alerts.staleAfterHours')}: ${staleHours}h • ${t('alerts.gracePeriodMinutes')}: ${graceMinutes}m • ${t('alerts.stuckAfterMinutes')}: ${stuckMinutes}m`
}

function formatDateTime(dateStr: string, language: string) {
  return new Intl.DateTimeFormat(language === 'it' ? 'it-IT' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(dateStr))
}

function formatDecimal(value: string | number, language: string) {
  const numeric = typeof value === 'string' ? Number(value) : value
  if (!Number.isFinite(numeric)) return '—'

  return new Intl.NumberFormat(language === 'it' ? 'it-IT' : 'en-US', {
    minimumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(numeric)
}

function ruleSummary(
  rule: Pick<AlertRule, 'alert_type' | 'conditions'>,
  t: (key: string, vars?: Record<string, string | number>) => string,
  language: string,
) {
  const conditions = (rule.conditions as Record<string, unknown>) ?? {}

  if (rule.alert_type === 'low_stock') {
    return t('alerts.ruleSentence.low_stock', {
      threshold: formatDecimal((conditions.threshold as number | undefined) ?? 10, language),
    })
  }

  if (rule.alert_type === 'bsr_drop') {
    return t('alerts.ruleSentence.bsr_drop', {
      percent: formatDecimal((conditions.drop_percent as number | undefined) ?? 20, language),
    })
  }

  if (rule.alert_type === 'price_change') {
    const minPrice = conditions.min_price as number | undefined
    const maxPrice = conditions.max_price as number | undefined

    if (minPrice != null && maxPrice != null) {
      return t('alerts.ruleSentence.price_change_range', {
        min: formatDecimal(minPrice, language),
        max: formatDecimal(maxPrice, language),
      })
    }
    if (minPrice != null) {
      return t('alerts.ruleSentence.price_change_min', {
        min: formatDecimal(minPrice, language),
      })
    }
    if (maxPrice != null) {
      return t('alerts.ruleSentence.price_change_max', {
        max: formatDecimal(maxPrice, language),
      })
    }
  }

  if (rule.alert_type === 'sync_failure') {
    return t('alerts.ruleSentence.sync_failure')
  }

  if (rule.alert_type === 'product_trend') {
    return t('alerts.ruleSentence.product_trend')
  }

  return ''
}

function ruleRecipients(rule: Pick<AlertRule, 'notification_emails'>, t: (key: string, vars?: Record<string, string | number>) => string) {
  if (!rule.notification_emails?.length) return t('alerts.noRecipients')
  if (rule.notification_emails.length === 1) return rule.notification_emails[0]
  return t('alerts.emailRecipientCount', { count: rule.notification_emails.length })
}

function ruleScope(rule: Pick<AlertRule, 'applies_to_accounts' | 'applies_to_asins'>, t: (key: string, vars?: Record<string, string | number>) => string) {
  if (rule.applies_to_asins?.length) return t('alerts.asinCount', { count: rule.applies_to_asins.length })
  if (rule.applies_to_accounts?.length) return t('alerts.accountCount', { count: rule.applies_to_accounts.length })
  return t('alerts.allTrackedItems')
}

function RuleFormDialog({
  open,
  onOpenChange,
  editRule,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  editRule: AlertRule | null
  onSaved: () => void
}) {
  const { t, language } = useTranslation()
  const { toast } = useToast()
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState(editRule?.name || '')
  const [alertType, setAlertType] = useState<AlertType>(editRule?.alert_type || 'low_stock')
  const [threshold, setThreshold] = useState(
    String((editRule?.conditions as Record<string, number>)?.threshold ?? 10)
  )
  const [dropPercent, setDropPercent] = useState(
    String((editRule?.conditions as Record<string, number>)?.drop_percent ?? 20)
  )
  const [minPrice, setMinPrice] = useState(
    String((editRule?.conditions as Record<string, number>)?.min_price ?? '')
  )
  const [maxPrice, setMaxPrice] = useState(
    String((editRule?.conditions as Record<string, number>)?.max_price ?? '')
  )
  const [staleAfterHours, setStaleAfterHours] = useState(
    syncConditionValue(editRule?.conditions as Record<string, unknown> | undefined, 'stale_after_hours', 24, 'stale_hours')
  )
  const [gracePeriodMinutes, setGracePeriodMinutes] = useState(
    syncConditionValue(editRule?.conditions as Record<string, unknown> | undefined, 'grace_period_minutes', 90)
  )
  const [stuckAfterMinutes, setStuckAfterMinutes] = useState(
    syncConditionValue(editRule?.conditions as Record<string, unknown> | undefined, 'stuck_after_minutes', 120)
  )
  const [emails, setEmails] = useState(editRule?.notification_emails?.join(', ') || '')

  useEffect(() => {
    if (!open) return

    setName(editRule?.name || '')
    setAlertType(editRule?.alert_type || 'low_stock')
    setThreshold(String((editRule?.conditions as Record<string, number>)?.threshold ?? 10))
    setDropPercent(String((editRule?.conditions as Record<string, number>)?.drop_percent ?? 20))
    setMinPrice(String((editRule?.conditions as Record<string, number>)?.min_price ?? ''))
    setMaxPrice(String((editRule?.conditions as Record<string, number>)?.max_price ?? ''))
    setStaleAfterHours(
      syncConditionValue(editRule?.conditions as Record<string, unknown> | undefined, 'stale_after_hours', 24, 'stale_hours')
    )
    setGracePeriodMinutes(
      syncConditionValue(editRule?.conditions as Record<string, unknown> | undefined, 'grace_period_minutes', 90)
    )
    setStuckAfterMinutes(
      syncConditionValue(editRule?.conditions as Record<string, unknown> | undefined, 'stuck_after_minutes', 120)
    )
    setEmails(editRule?.notification_emails?.join(', ') || '')
  }, [editRule, open])

  const previewSummary = ruleSummary(
    {
      alert_type: alertType,
      conditions: {
        threshold: Number(threshold),
        drop_percent: Number(dropPercent),
        min_price: minPrice === '' ? undefined : Number(minPrice),
        max_price: maxPrice === '' ? undefined : Number(maxPrice),
        stale_after_hours: Number(staleAfterHours),
        grace_period_minutes: Number(gracePeriodMinutes),
        stuck_after_minutes: Number(stuckAfterMinutes),
      },
    },
    t,
    language,
  )

  const emailList = emails
    .split(',')
    .map((email) => email.trim())
    .filter(Boolean)

  const handleSubmit = async () => {
    if (!name.trim()) return

    if (emailList.some((email) => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))) {
      toast({ title: t('alerts.emailValidation'), variant: 'destructive' })
      return
    }

    if (alertType === 'price_change' && minPrice === '' && maxPrice === '') {
      toast({ title: t('alerts.priceLimitRequired'), variant: 'destructive' })
      return
    }

    if (
      alertType === 'price_change' &&
      minPrice !== '' &&
      maxPrice !== '' &&
      Number(minPrice) > Number(maxPrice)
    ) {
      toast({ title: t('alerts.priceLimitInvalid'), variant: 'destructive' })
      return
    }

    setSaving(true)

    let conditions: Record<string, unknown> = {}
    if (alertType === 'low_stock') {
      conditions = { threshold: Number(threshold) || 10 }
    } else if (alertType === 'bsr_drop') {
      conditions = { drop_percent: Number(dropPercent) || 20 }
    } else if (alertType === 'price_change') {
      conditions = {
        min_price: minPrice !== '' ? Number(minPrice) : null,
        max_price: maxPrice !== '' ? Number(maxPrice) : null,
      }
    } else if (alertType === 'sync_failure') {
      conditions = {
        stale_after_hours: Number(staleAfterHours) || 24,
        grace_period_minutes: Number(gracePeriodMinutes) || 90,
        stuck_after_minutes: Number(stuckAfterMinutes) || 120,
      }
    }

    const payload = {
      name: name.trim(),
      alert_type: alertType,
      conditions,
      notification_emails: emailList.length > 0 ? emailList : null,
    }

    try {
      if (editRule) {
        await alertsApi.updateRule(editRule.id, payload)
        toast({ title: t('alerts.ruleUpdated') })
      } else {
        await alertsApi.createRule(payload)
        toast({ title: t('alerts.ruleCreated') })
      }
      onOpenChange(false)
      onSaved()
    } catch {
      toast({ title: t('alerts.ruleSaveFailed'), variant: 'destructive' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{editRule ? t('alerts.editRule') : t('alerts.addRule')}</DialogTitle>
          <DialogDescription>{t('alerts.ruleFormDesc')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-1">
          <div className="rounded-lg border border-border/70 bg-muted/20 p-4">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              {t('alerts.preview')}
            </p>
            <p className="mt-2 text-sm font-medium text-foreground">{previewSummary}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {t('alerts.previewRecipients', {
                recipients:
                  emailList.length === 0
                    ? t('alerts.noRecipients')
                    : emailList.length === 1
                    ? emailList[0]
                    : t('alerts.emailRecipientCount', { count: emailList.length }),
              })}
            </p>
          </div>

          <div className="space-y-4 rounded-lg border border-border/70 p-4">
            <div className="space-y-1">
              <p className="text-sm font-medium">{t('alerts.sectionMonitor')}</p>
              <p className="text-xs text-muted-foreground">{t('alerts.sectionMonitorDesc')}</p>
            </div>

            <div className="space-y-2">
              <Label>{t('alerts.ruleName')}</Label>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={t('alerts.ruleNamePlaceholder')}
              />
            </div>

            <div className="space-y-2">
              <Label>{t('alerts.alertType')}</Label>
              <Select value={alertType} onValueChange={(value) => setAlertType(value as AlertType)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ALERT_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {t(`alerts.type.${type}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">{t(`alerts.typeHelp.${alertType}`)}</p>
            </div>
          </div>

          <div className="space-y-4 rounded-lg border border-border/70 p-4">
            <div className="space-y-1">
              <p className="text-sm font-medium">{t('alerts.sectionCondition')}</p>
              <p className="text-xs text-muted-foreground">{t('alerts.sectionConditionDesc')}</p>
            </div>

            {alertType === 'low_stock' && (
              <div className="space-y-2">
                <Label>{t('alerts.threshold')}</Label>
                <Input type="number" min={0} value={threshold} onChange={(event) => setThreshold(event.target.value)} />
                <p className="text-xs text-muted-foreground">{t('alerts.thresholdHelp')}</p>
              </div>
            )}

            {alertType === 'bsr_drop' && (
              <div className="space-y-2">
                <Label>{t('alerts.dropPercent')}</Label>
                <Input type="number" min={1} max={100} value={dropPercent} onChange={(event) => setDropPercent(event.target.value)} />
                <p className="text-xs text-muted-foreground">{t('alerts.dropPercentHelp')}</p>
              </div>
            )}

            {alertType === 'price_change' && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>{t('alerts.minPrice')}</Label>
                  <Input type="number" step="0.01" value={minPrice} onChange={(event) => setMinPrice(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>{t('alerts.maxPrice')}</Label>
                  <Input type="number" step="0.01" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} />
                </div>
              </div>
            )}

            {alertType === 'sync_failure' && (
              <div className="space-y-4 rounded-md bg-muted/40 px-3 py-3">
                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="space-y-2">
                    <Label>{t('alerts.staleAfterHours')}</Label>
                    <Input
                      type="number"
                      min={1}
                      value={staleAfterHours}
                      onChange={(event) => setStaleAfterHours(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>{t('alerts.gracePeriodMinutes')}</Label>
                    <Input
                      type="number"
                      min={0}
                      value={gracePeriodMinutes}
                      onChange={(event) => setGracePeriodMinutes(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>{t('alerts.stuckAfterMinutes')}</Label>
                    <Input
                      type="number"
                      min={1}
                      value={stuckAfterMinutes}
                      onChange={(event) => setStuckAfterMinutes(event.target.value)}
                    />
                  </div>
                </div>
                <p className="text-sm text-muted-foreground">{t('alerts.syncThresholdHelp')}</p>
              </div>
            )}
          </div>

          <div className="space-y-4 rounded-lg border border-border/70 p-4">
            <div className="space-y-1">
              <p className="text-sm font-medium">{t('alerts.sectionNotify')}</p>
              <p className="text-xs text-muted-foreground">{t('alerts.sectionNotifyDesc')}</p>
            </div>

            <div className="space-y-2">
              <Label>{t('alerts.notificationEmails')}</Label>
              <Input
                value={emails}
                onChange={(event) => setEmails(event.target.value)}
                placeholder="email1@example.com, email2@example.com"
              />
              <p className="text-xs text-muted-foreground">{t('alerts.emailsHelp')}</p>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSubmit} disabled={saving || !name.trim()}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RulesTab() {
  const { t, language } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editRule, setEditRule] = useState<AlertRule | null>(null)
  const [ruleToDelete, setRuleToDelete] = useState<AlertRule | null>(null)

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['alert-rules'],
    queryFn: alertsApi.listRules,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_enabled }: { id: string; is_enabled: boolean }) =>
      alertsApi.updateRule(id, { is_enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
      queryClient.invalidateQueries({ queryKey: ['alerts-summary'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => alertsApi.deleteRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
      queryClient.invalidateQueries({ queryKey: ['alerts-summary'] })
      toast({ title: t('alerts.ruleDeleted') })
      setRuleToDelete(null)
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <Card className="border-border/60">
        <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <h2 className="text-base font-semibold">{t('alerts.rules')}</h2>
            <p className="text-sm text-muted-foreground">{t('alerts.rulesIntro')}</p>
          </div>
          <Button
            onClick={() => {
              setEditRule(null)
              setDialogOpen(true)
            }}
          >
            <Plus className="mr-2 h-4 w-4" />
            {t('alerts.addRule')}
          </Button>
        </CardContent>
      </Card>

      {rules.length === 0 ? (
        <Card className="border-dashed border-border/70">
          <CardContent className="flex flex-col items-center justify-center gap-4 py-14 text-center">
            <Bell className="h-10 w-10 text-muted-foreground" />
            <div className="space-y-2">
              <p className="text-lg font-medium">{t('alerts.noRulesTitle')}</p>
              <p className="max-w-xl text-sm text-muted-foreground">{t('alerts.noRulesDesc')}</p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              <Badge variant="outline">{t('alerts.suggestedRule.low_stock')}</Badge>
              <Badge variant="outline">{t('alerts.suggestedRule.sync_failure')}</Badge>
              <Badge variant="outline">{t('alerts.suggestedRule.price_change')}</Badge>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {rules.map((rule) => (
            <Card key={rule.id} className={cn('border-border/60', !rule.is_enabled && 'bg-muted/10')}>
              <CardContent className="space-y-5 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      {alertTypeBadge(rule.alert_type, t)}
                      <Badge variant={rule.is_enabled ? 'success' : 'secondary'}>
                        {rule.is_enabled ? t('alerts.enabled') : t('alerts.disabled')}
                      </Badge>
                    </div>
                    <div className="space-y-1">
                      <h3 className="text-lg font-semibold leading-tight">{rule.name}</h3>
                      <p className="text-sm text-muted-foreground">{ruleSummary(rule, t, language)}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 rounded-full border border-border/70 px-3 py-1.5">
                    <span className="text-xs font-medium text-muted-foreground">
                      {rule.is_enabled ? t('alerts.enabled') : t('alerts.disabled')}
                    </span>
                    <Switch
                      checked={rule.is_enabled}
                      onCheckedChange={(checked) =>
                        toggleMutation.mutate({ id: rule.id, is_enabled: checked })
                      }
                    />
                  </div>
                </div>

                <div className="grid gap-3 text-sm sm:grid-cols-2">
                  <div className="rounded-lg border border-border/60 bg-background/60 p-3">
                    <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {t('alerts.conditionLabel')}
                    </p>
                    <p className="mt-2 font-medium text-foreground">
                      {rule.alert_type === 'sync_failure'
                        ? syncRuleSummary(rule.conditions as Record<string, unknown> | undefined, t)
                        : ruleSummary(rule, t, language)}
                    </p>
                  </div>

                  <div className="rounded-lg border border-border/60 bg-background/60 p-3">
                    <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {t('alerts.notifyLabel')}
                    </p>
                    <p className="mt-2 font-medium text-foreground">{ruleRecipients(rule, t)}</p>
                  </div>

                  <div className="rounded-lg border border-border/60 bg-background/60 p-3">
                    <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {t('alerts.appliesTo')}
                    </p>
                    <p className="mt-2 font-medium text-foreground">{ruleScope(rule, t)}</p>
                  </div>

                  <div className="rounded-lg border border-border/60 bg-background/60 p-3">
                    <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                      {t('alerts.lastTriggered')}
                    </p>
                    <p className="mt-2 font-medium text-foreground">
                      {rule.last_triggered_at ? formatDate(rule.last_triggered_at) : t('alerts.never')}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {formatNumber(rule.alert_count)} {t('alerts.triggeredLabel')}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditRule(rule)
                      setDialogOpen(true)
                    }}
                  >
                    <Pencil className="mr-2 h-4 w-4" />
                    {t('alerts.editRule')}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRuleToDelete(rule)}
                  >
                    <Trash2 className="mr-2 h-4 w-4 text-destructive" />
                    {t('alerts.deleteRuleAction')}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <RuleFormDialog
        key={editRule?.id || 'new'}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editRule={editRule}
        onSaved={() => {
          queryClient.invalidateQueries({ queryKey: ['alert-rules'] })
          queryClient.invalidateQueries({ queryKey: ['alerts-summary'] })
        }}
      />

      <Dialog open={Boolean(ruleToDelete)} onOpenChange={(open) => !open && setRuleToDelete(null)}>
        <DialogContent className="sm:max-w-[440px]">
          <DialogHeader>
            <DialogTitle>{t('alerts.deleteRuleTitle')}</DialogTitle>
            <DialogDescription>{t('alerts.deleteRuleDesc')}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRuleToDelete(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={() => ruleToDelete && deleteMutation.mutate(ruleToDelete.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('alerts.deleteRuleAction')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function HistoryTab({
  highlightedAlertId,
}: {
  highlightedAlertId: string | null
}) {
  const { t, language } = useTranslation()
  const queryClient = useQueryClient()
  const [severityFilter, setSeverityFilter] = useState<string>('all')
  const [readFilter, setReadFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [offset, setOffset] = useState(0)
  const limit = 50
  const hasActiveFilters = severityFilter !== 'all' || readFilter !== 'all' || typeFilter !== 'all'

  useEffect(() => {
    setOffset(0)
  }, [severityFilter, readFilter, typeFilter])

  const params: Record<string, unknown> = { limit, offset }
  if (severityFilter !== 'all') params.severity = severityFilter
  if (readFilter !== 'all') params.status = readFilter
  if (typeFilter !== 'all') params.type = typeFilter

  const { data: unreadData } = useQuery({
    queryKey: ['unread-alert-count'],
    queryFn: alertsApi.getUnreadCount,
    staleTime: 30000,
  })

  const { data: alertsResponse, isLoading } = useQuery({
    queryKey: ['alert-history', params],
    queryFn: () => alertsApi.getAlerts(params as Parameters<typeof alertsApi.getAlerts>[0]),
  })

  const alerts = alertsResponse?.items ?? []
  const unreadCount = unreadData?.count ?? 0
  const hasMore = alertsResponse?.has_more ?? false
  const total = alertsResponse?.total ?? 0
  const pageStart = total === 0 ? 0 : offset + 1
  const pageEnd = offset + alerts.length

  const markReadMutation = useMutation({
    mutationFn: (id: string) => alertsApi.markAsRead(id),
    onMutate: async (id) => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: ['alert-history'] }),
        queryClient.cancelQueries({ queryKey: ['unread-alert-count'] }),
        queryClient.cancelQueries({ queryKey: ['recent-alerts'] }),
      ])

      return optimisticallyMarkAlertRead(queryClient, id)
    },
    onError: (_error, _id, snapshot) => {
      restoreAlertQuerySnapshot(queryClient, snapshot)
    },
    onSuccess: (response) => {
      queryClient.setQueryData(['unread-alert-count'], { count: response.unread_count })
      queryClient.invalidateQueries({ queryKey: ['alerts-summary'] })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-history'] })
      queryClient.invalidateQueries({ queryKey: ['recent-alerts'] })
    },
  })

  const markAllReadMutation = useMutation({
    mutationFn: () => alertsApi.markAllAsRead(),
    onMutate: async () => {
      await Promise.all([
        queryClient.cancelQueries({ queryKey: ['alert-history'] }),
        queryClient.cancelQueries({ queryKey: ['unread-alert-count'] }),
        queryClient.cancelQueries({ queryKey: ['recent-alerts'] }),
      ])

      return optimisticallyMarkAllAlertsRead(queryClient)
    },
    onError: (_error, _variables, snapshot) => {
      restoreAlertQuerySnapshot(queryClient, snapshot)
    },
    onSuccess: (response) => {
      queryClient.setQueryData(['unread-alert-count'], { count: response.unread_count })
      queryClient.invalidateQueries({ queryKey: ['alerts-summary'] })
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-history'] })
      queryClient.invalidateQueries({ queryKey: ['recent-alerts'] })
    },
  })

  useEffect(() => {
    if (!highlightedAlertId || alerts.length === 0) return

    const element = document.querySelector<HTMLElement>(`[data-alert-id="${highlightedAlertId}"]`)
    if (!element) return

    requestAnimationFrame(() => {
      element.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
  }, [alerts, highlightedAlertId])

  const clearFilters = () => {
    setSeverityFilter('all')
    setReadFilter('all')
    setTypeFilter('all')
  }

  return (
    <div className="space-y-4">
      <Card className="border-border/60">
        <CardContent className="space-y-4 p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1">
              <h2 className="text-base font-semibold">{t('alerts.historyFiltersTitle')}</h2>
              <p className="text-sm text-muted-foreground">
                {hasActiveFilters
                  ? t('alerts.filteredResults', { count: alerts.length })
                  : t('alerts.historyFiltersDesc')}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {hasActiveFilters && (
                <Button variant="ghost" size="sm" onClick={clearFilters}>
                  <FilterX className="mr-2 h-4 w-4" />
                  {t('alerts.clearFilters')}
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => markAllReadMutation.mutate()}
                disabled={markAllReadMutation.isPending || unreadCount === 0}
              >
                {markAllReadMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                )}
                {t('alerts.markAllRead')}
              </Button>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-2">
              <Label>{t('alerts.severity')}</Label>
              <Select value={severityFilter} onValueChange={setSeverityFilter}>
                <SelectTrigger><SelectValue placeholder={t('alerts.severity')} /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('alerts.allSeverities')}</SelectItem>
                  <SelectItem value="critical">{t('alerts.severity.critical')}</SelectItem>
                  <SelectItem value="warning">{t('alerts.severity.warning')}</SelectItem>
                  <SelectItem value="info">{t('alerts.severity.info')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>{t('alerts.statusLabel')}</Label>
              <Select value={readFilter} onValueChange={setReadFilter}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('alerts.allStatus')}</SelectItem>
                  <SelectItem value="unread">{t('alerts.unread')}</SelectItem>
                  <SelectItem value="read">{t('alerts.read')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>{t('alerts.alertType')}</Label>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('alerts.allTypes')}</SelectItem>
                  {ALERT_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>{t(`alerts.type.${type}`)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : alerts.length === 0 ? (
        <Card className={cn(hasActiveFilters && 'border-dashed border-border/70')}>
          <CardContent className="flex flex-col items-center justify-center gap-3 py-14 text-center">
            {hasActiveFilters ? (
              <FilterX className="h-10 w-10 text-muted-foreground" />
            ) : (
              <CheckCircle2 className="h-10 w-10 text-muted-foreground" />
            )}
            <div className="space-y-2">
              <p className="text-lg font-medium">
                {hasActiveFilters ? t('alerts.emptyFilteredTitle') : t('alerts.noAlerts')}
              </p>
              <p className="max-w-xl text-sm text-muted-foreground">
                {hasActiveFilters ? t('alerts.emptyFilteredDesc') : t('alerts.noAlertsDesc')}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <Card
              key={alert.id}
              data-alert-id={alert.id}
              className={cn(
                'border-border/60 transition-colors',
                !alert.is_read && 'border-primary/30 bg-primary/[0.03]',
                highlightedAlertId === alert.id && 'ring-2 ring-primary/30 ring-offset-2'
              )}
            >
              <CardContent className="flex items-start gap-3 px-4 py-3">
                <div className="mt-0.5">{severityIcon(alert.severity)}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {alertTypeBadge(alert.alert_type, t)}
                    {severityBadge(alert.severity)}
                    {!alert.is_read && (
                      <Badge variant="outline" className="border-primary/30 text-primary">
                        {t('alerts.unread')}
                      </Badge>
                    )}
                    {alert.alert_type === 'sync_failure' && typeof alert.details.incident_label === 'string' && (
                      <Badge variant="outline">{alert.details.incident_label}</Badge>
                    )}
                    {alert.resolved_at && <Badge variant="outline">{t('alerts.resolved')}</Badge>}
                    {alert.asin && <Badge variant="outline">ASIN: {alert.asin}</Badge>}
                  </div>
                  <p className={cn('mt-1 text-sm', !alert.is_read && 'font-medium')}>
                    {alert.message}
                  </p>
                  {typeof alert.details.recommended_action === 'string' && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {t('alerts.recommendedAction')}: {alert.details.recommended_action}
                    </p>
                  )}
                  <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {timeAgo(alert.triggered_at)}
                    </span>
                    <span title={formatDateTime(alert.triggered_at, language)}>
                      {formatDate(alert.triggered_at)}
                    </span>
                    {alert.rule_name && <span>{alert.rule_name}</span>}
                  </div>
                </div>
                <div className="ml-2 shrink-0">
                  {!alert.is_read ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 px-2 text-xs"
                      onClick={() => markReadMutation.mutate(alert.id)}
                      disabled={markReadMutation.isPending && markReadMutation.variables === alert.id}
                    >
                      {markReadMutation.isPending && markReadMutation.variables === alert.id ? (
                        <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                      )}
                      {t('alerts.markRead')}
                    </Button>
                  ) : (
                    <span className="mt-2 block h-2 w-2 rounded-full bg-muted-foreground/30" />
                  )}
                </div>
              </CardContent>
            </Card>
          ))}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <p className="text-sm text-muted-foreground">
              {t('alerts.pageRange', { start: pageStart, end: pageEnd, total })}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOffset((current) => Math.max(0, current - limit))}
                disabled={offset === 0}
              >
                {t('alerts.previousPage')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setOffset((current) => current + limit)}
                disabled={!hasMore}
              >
                {t('alerts.nextPage')}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Alerts() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const [highlightedAlertId, setHighlightedAlertId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('history')

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['alerts-summary'],
    queryFn: alertsApi.getSummary,
  })

  useEffect(() => {
    const nextAlertId = (location.state as { focusAlertId?: string } | null)?.focusAlertId ?? null
    if (!nextAlertId) return

    setHighlightedAlertId(nextAlertId)
    navigate(location.pathname, { replace: true, state: null })
  }, [location.pathname, location.state, navigate])

  useEffect(() => {
    if (!highlightedAlertId) return

    const timeout = window.setTimeout(() => {
      setHighlightedAlertId(null)
    }, 4000)

    return () => window.clearTimeout(timeout)
  }, [highlightedAlertId])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t('alerts.title')}</h1>
        <p className="text-muted-foreground">{t('alerts.subtitle')}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
            <div className="space-y-1">
              <CardDescription className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {t('alerts.summaryUnread')}
              </CardDescription>
              <CardTitle className="text-3xl font-semibold tracking-tight">
                {summaryLoading ? '—' : formatNumber(summary?.unread_count ?? 0)}
              </CardTitle>
            </div>
            <BellRing className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="pt-0 text-sm text-muted-foreground">
            {t('alerts.summaryUnreadDesc')}
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
            <div className="space-y-1">
              <CardDescription className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {t('alerts.summaryCritical')}
              </CardDescription>
              <CardTitle className="text-3xl font-semibold tracking-tight">
                {summaryLoading ? '—' : formatNumber(summary?.critical_count ?? 0)}
              </CardTitle>
            </div>
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="pt-0 text-sm text-muted-foreground">
            {t('alerts.summaryCriticalDesc')}
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
            <div className="space-y-1">
              <CardDescription className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                {t('alerts.summaryActiveRules')}
              </CardDescription>
              <CardTitle className="text-3xl font-semibold tracking-tight">
                {summaryLoading ? '—' : formatNumber(summary?.active_rule_count ?? 0)}
              </CardTitle>
            </div>
            <Mail className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="pt-0 text-sm text-muted-foreground">
            {t('alerts.summaryActiveRulesDesc', { total: summary?.total_rule_count ?? 0 })}
          </CardContent>
        </Card>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="history" className="gap-2">
            <span>{t('alerts.history')}</span>
            <Badge variant="secondary" className="px-2 py-0 text-[11px]">
              {formatNumber(summary?.unread_count ?? 0)}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="rules" className="gap-2">
            <span>{t('alerts.rules')}</span>
            <Badge variant="secondary" className="px-2 py-0 text-[11px]">
              {formatNumber(summary?.active_rule_count ?? 0)}
            </Badge>
          </TabsTrigger>
        </TabsList>
        <TabsContent value="history" className="mt-4">
          <HistoryTab highlightedAlertId={highlightedAlertId} />
        </TabsContent>
        <TabsContent value="rules" className="mt-4">
          <RulesTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
