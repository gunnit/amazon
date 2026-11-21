import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RotateCcw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { catalogMonitorApi } from '@/services/api'
import { useAuthStore } from '@/store/authStore'
import { QUALITY_RULE_KEYS } from '@/types'
import type { QualityRuleConfig, QualityRuleKey, QualityRuleOverride, RuleParamValue } from '@/types'
import type { TabProps } from '@/components/catalog/types'
import { ruleLabel } from './describe'

const ALL = '__all__'

// Same marketplaces the account form offers (Settings > Accounts).
const MARKETPLACES = [
  { id: 'A1PA6795UKMFR9', code: 'DE' },
  { id: 'APJ6JRA9NG5V4', code: 'IT' },
  { id: 'A1F83G8C2ARO7P', code: 'UK' },
  { id: 'A13V1IB3VIYZZH', code: 'FR' },
  { id: 'A1RKKUPIHCS9HS', code: 'ES' },
]

const norm = (v: string | null | undefined) => v || ''
const sameScope = (o: QualityRuleOverride, marketplace: string, productType: string) =>
  norm(o.marketplace_id) === marketplace && norm(o.product_type) === productType

interface ParamFieldProps {
  name: string
  value: RuleParamValue
  disabled: boolean
  label: string
  onChange: (value: RuleParamValue) => void
}

/** Numbers edit as numbers, lists as comma-separated text; invalid input is not committed. */
function ParamField({ name, value, disabled, label, onChange }: ParamFieldProps) {
  const isList = Array.isArray(value)
  const [text, setText] = useState(isList ? value.join(', ') : String(value))
  const id = `cm-param-${name}`
  return (
    <div className="space-y-0.5">
      <Label htmlFor={id} className="text-xs font-normal text-muted-foreground">
        {label}
      </Label>
      <Input
        id={id}
        className={isList ? 'h-8 min-w-[220px]' : 'h-8 w-24'}
        type={isList ? 'text' : 'number'}
        step={name === 'min_fill' ? 0.01 : 1}
        min={0}
        value={text}
        disabled={disabled}
        onChange={(e) => {
          setText(e.target.value)
          if (isList) {
            onChange(
              e.target.value
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean),
            )
          } else if (e.target.value !== '' && Number.isFinite(Number(e.target.value))) {
            onChange(Number(e.target.value))
          }
        }}
      />
    </div>
  )
}

export function RulesPanel({ t, toast }: Pick<TabProps, 't' | 'toast'>) {
  const queryClient = useQueryClient()
  const isAdmin = useAuthStore((s) => s.organization?.my_role) === 'admin'

  const [marketplace, setMarketplace] = useState('')
  const [productType, setProductType] = useState('')
  const [draft, setDraft] = useState<QualityRuleOverride[]>([])
  const [dirty, setDirty] = useState(false)
  // bumped when a row is reset so its parameter inputs reload their text
  const [resetNonce, setResetNonce] = useState(0)

  const query = useQuery({
    queryKey: ['catalog-monitor', 'rules'],
    queryFn: () => catalogMonitorApi.getRules(),
  })
  const defaults = query.data?.defaults

  useEffect(() => {
    if (query.data) {
      setDraft(query.data.overrides)
      setDirty(false)
      setResetNonce((n) => n + 1)
      setResetNonce((n) => n + 1)
    }
  }, [query.data])

  const save = useMutation({
    mutationFn: () =>
      catalogMonitorApi.putRules(
        draft.map(({ marketplace_id, product_type, rule_key, enabled, mandatory, params }) => ({
          marketplace_id: marketplace_id || null,
          product_type: product_type || null,
          rule_key,
          enabled,
          mandatory,
          params,
        })),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(['catalog-monitor', 'rules'], data)
      toast({ title: t('cm.rules.saved'), description: t('cm.rules.savedHint') })
    },
    onError: (error) => {
      const status = (error as { response?: { status?: number } })?.response?.status
      toast({
        title: status === 403 ? t('cm.rules.adminOnly') : t('cm.rules.saveError'),
        variant: 'destructive',
      })
    },
  })

  const scopeProductType = productType.trim().toUpperCase()
  const findOverride = (key: QualityRuleKey) =>
    draft.find((o) => o.rule_key === key && sameScope(o, marketplace, scopeProductType))

  /** What applies in this scope: its own override, else the global default. */
  const effective = (key: QualityRuleKey): QualityRuleConfig | undefined => {
    const base = defaults?.[key]
    if (!base) return undefined
    const o = findOverride(key)
    if (!o) return base
    return {
      key,
      enabled: o.enabled,
      mandatory: o.mandatory,
      params: { ...base.params, ...(o.params ?? {}) },
    }
  }

  const update = (key: QualityRuleKey, patch: Partial<QualityRuleConfig>) => {
    const current = effective(key)
    if (!current) return
    const next: QualityRuleOverride = {
      marketplace_id: marketplace || null,
      product_type: scopeProductType || null,
      rule_key: key,
      enabled: patch.enabled ?? current.enabled,
      mandatory: patch.mandatory ?? current.mandatory,
      params: patch.params ?? current.params,
    }
    setDraft((rows) => [
      ...rows.filter((o) => !(o.rule_key === key && sameScope(o, marketplace, scopeProductType))),
      next,
    ])
    setDirty(true)
  }

  const reset = (key: QualityRuleKey) => {
    setDraft((rows) =>
      rows.filter((o) => !(o.rule_key === key && sameScope(o, marketplace, scopeProductType))),
    )
    setResetNonce((n) => n + 1)
    setResetNonce((n) => n + 1)
    setDirty(true)
  }

  const overrideCount = useMemo(() => draft.length, [draft])
  const disabled = !isAdmin

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('cm.rules.title')}</CardTitle>
        <CardDescription>{t('cm.rules.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!isAdmin && (
          <p className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
            {t('cm.rules.readOnly')}
          </p>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px]">
            <Label>{t('cm.rules.marketplace')}</Label>
            <Select
              value={marketplace || ALL}
              onValueChange={(v) => setMarketplace(v === ALL ? '' : v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t('cm.rules.allMarketplaces')}</SelectItem>
                {MARKETPLACES.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {t(`marketplace.${m.code}`)} ({m.code})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="min-w-[200px]">
            <Label htmlFor="cm-rules-product-type">{t('cm.rules.productType')}</Label>
            <Input
              id="cm-rules-product-type"
              value={productType}
              maxLength={100}
              placeholder={t('cm.rules.productTypePlaceholder')}
              onChange={(e) => setProductType(e.target.value)}
            />
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-muted-foreground">
              {t('cm.rules.overrideCount', { count: overrideCount })}
            </span>
            {isAdmin && (
              <Button onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
                {save.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('common.save')}
              </Button>
            )}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{t('cm.rules.scopeHint')}</p>

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('cm.rules.col.rule')}</TableHead>
                <TableHead className="text-center">{t('cm.rules.col.enabled')}</TableHead>
                <TableHead className="text-center">{t('cm.rules.col.mandatory')}</TableHead>
                <TableHead>{t('cm.rules.col.params')}</TableHead>
                <TableHead className="w-[1%]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.isLoading && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center">
                    <Loader2 className="mx-auto h-5 w-5 animate-spin" />
                  </TableCell>
                </TableRow>
              )}
              {query.isError && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-destructive">
                    {t('cm.rules.loadError')}
                  </TableCell>
                </TableRow>
              )}
              {defaults &&
                QUALITY_RULE_KEYS.map((key) => {
                  const cfg = effective(key)
                  if (!cfg) return null
                  const customised = findOverride(key) !== undefined
                  return (
                    <TableRow key={`${marketplace}|${scopeProductType}|${key}`}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{ruleLabel(t, key)}</span>
                          {customised && (
                            <Badge variant="outline" className="text-[10px]">
                              {t('cm.rules.customised')}
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">{t(`cm.ruleHelp.${key}`)}</p>
                      </TableCell>
                      <TableCell className="text-center">
                        <Switch
                          checked={cfg.enabled}
                          disabled={disabled}
                          aria-label={`${ruleLabel(t, key)}: ${t('cm.rules.col.enabled')}`}
                          onCheckedChange={(v) => update(key, { enabled: v })}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        <Checkbox
                          checked={cfg.mandatory}
                          disabled={disabled}
                          aria-label={`${ruleLabel(t, key)}: ${t('cm.rules.col.mandatory')}`}
                          onCheckedChange={(v) => update(key, { mandatory: v === true })}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-3">
                          {Object.entries(cfg.params).map(([name, value]) => (
                            <ParamField
                              key={`${name}|${resetNonce}`}
                              name={name}
                              value={value}
                              disabled={disabled}
                              label={t(`cm.param.${name}`)}
                              onChange={(v) => update(key, { params: { ...cfg.params, [name]: v } })}
                            />
                          ))}
                          {Object.keys(cfg.params).length === 0 && (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {customised && !disabled && (
                          <Button
                            variant="ghost"
                            size="sm"
                            title={t('cm.rules.reset')}
                            aria-label={`${ruleLabel(t, key)}: ${t('cm.rules.reset')}`}
                            onClick={() => reset(key)}
                          >
                            <RotateCcw className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
