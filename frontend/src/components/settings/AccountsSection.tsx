import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  AlertTriangle,
  Check,
  Clock,
  Edit,
  Eye,
  History,
  KeyRound,
  Link2,
  Loader2,
  Megaphone,
  Plus,
  RefreshCw,
  Search,
  Store,
  Trash2,
} from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { cn, formatDate } from '@/lib/utils'
import { isPlaceholderAccountName } from '@/lib/accountNaming'
import { accountsApi, authApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import type {
  AccountSummary,
  AccountType,
  AdsConnectionState,
  AdvertisingProfile,
  AmazonAccount,
  ApiKeysResponse,
  BackfillStatus,
  SyncStatus,
} from '@/types'

type ConnectionMode = 'manual' | 'sp' | 'ads'
type StatusFilter = 'all' | 'connected' | 'partial' | 'missing' | 'error'

type AccountPayload = {
  account_name: string
  account_type: AccountType
  marketplace_id: string
  marketplace_country: string
  refresh_token?: string
  advertising_refresh_token?: string
  advertising_profile_id?: string
}

const marketplaces = [
  { id: 'A1PA6795UKMFR9', country: 'DE', nameKey: 'marketplace.DE' },
  { id: 'APJ6JRA9NG5V4', country: 'IT', nameKey: 'marketplace.IT' },
  { id: 'A1F83G8C2ARO7P', country: 'UK', nameKey: 'marketplace.UK' },
  { id: 'A13V1IB3VIYZZH', country: 'FR', nameKey: 'marketplace.FR' },
  { id: 'A1RKKUPIHCS9HS', country: 'ES', nameKey: 'marketplace.ES' },
]

function connectionState(account: AmazonAccount): StatusFilter {
  if (account.sync_status === 'error') return 'error'
  if (account.has_refresh_token && account.has_advertising_refresh_token && account.advertising_profile_id) {
    return 'connected'
  }
  if (account.has_refresh_token || account.has_advertising_refresh_token || account.advertising_profile_id) {
    return 'partial'
  }
  return 'missing'
}

function resolveAdsState(account: AmazonAccount): AdsConnectionState {
  if (account.ads_connection_state) return account.ads_connection_state
  if (account.has_ads_client_credentials === false) return 'missing_client_credentials'
  if (!account.has_advertising_refresh_token) return 'missing_refresh_token'
  if (!account.advertising_profile_id) return 'missing_profile'
  return 'ok'
}

function StatusBadge({ status }: { status: SyncStatus }) {
  const { t } = useTranslation()
  const config = {
    success: { label: t('accounts.status.synced'), icon: Check, className: 'bg-emerald-500 text-white' },
    syncing: { label: t('accounts.status.syncing'), icon: Loader2, className: 'bg-blue-500 text-white' },
    error: { label: t('accounts.status.error'), icon: AlertCircle, className: '' },
    pending: { label: t('accounts.status.pending'), icon: Clock, className: '' },
  }[status]
  const Icon = config.icon

  return (
    <Badge
      variant={status === 'error' ? 'destructive' : status === 'pending' ? 'outline' : 'secondary'}
      className={cn('gap-1 whitespace-nowrap', config.className)}
    >
      <Icon className={cn('h-3 w-3', status === 'syncing' && 'animate-spin')} />
      {config.label}
    </Badge>
  )
}

function BackfillBadge({ account }: { account: AmazonAccount }) {
  const { t } = useTranslation()
  const status = account.last_backfill_status as BackfillStatus | null | undefined
  if (!status) {
    return (
      <Badge variant="outline" className="gap-1 whitespace-nowrap text-muted-foreground">
        {t('accounts.backfill.never')}
      </Badge>
    )
  }
  const config: Record<BackfillStatus, { label: string; icon: typeof Check; className?: string; variant?: 'destructive' | 'outline' | 'secondary' }> = {
    running: { label: t('accounts.backfill.running'), icon: Loader2, className: 'bg-blue-500 text-white', variant: 'secondary' },
    success: { label: t('accounts.backfill.success'), icon: Check, className: 'bg-emerald-500 text-white', variant: 'secondary' },
    partial: { label: t('accounts.backfill.partial'), icon: AlertTriangle, variant: 'outline', className: 'border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-400' },
    error: { label: t('accounts.backfill.error'), icon: AlertCircle, variant: 'destructive' },
  }
  const { label, icon: Icon, className, variant } = config[status]
  const tooltipParts = [
    account.last_backfill_range_start && account.last_backfill_range_end
      ? `${account.last_backfill_range_start} → ${account.last_backfill_range_end}`
      : null,
    account.last_backfill_records != null ? `${account.last_backfill_records} rec` : null,
    account.last_backfill_error || null,
  ].filter(Boolean)
  return (
    <Badge variant={variant} className={cn('gap-1 whitespace-nowrap', className)} title={tooltipParts.join(' · ') || undefined}>
      <Icon className={cn('h-3 w-3', status === 'running' && 'animate-spin')} />
      {label}
    </Badge>
  )
}

function CredentialBadge({
  connected,
  label,
}: {
  connected: boolean
  label: string
}) {
  return connected ? (
    <Badge className="gap-1 whitespace-nowrap bg-emerald-500 text-white">
      <Check className="h-3 w-3" />
      {label}
    </Badge>
  ) : (
    <Badge variant="outline" className="gap-1 whitespace-nowrap border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-400">
      <AlertTriangle className="h-3 w-3" />
      {label}
    </Badge>
  )
}

function AdsStateBadge({ account }: { account: AmazonAccount }) {
  const { t } = useTranslation()
  const state = resolveAdsState(account)
  const label = t(`accounts.adsState.${state}`)
  const detail = account.ads_connection_detail || undefined
  if (state === 'ok') {
    return (
      <Badge className="gap-1 whitespace-nowrap bg-emerald-500 text-white" title={detail}>
        <Check className="h-3 w-3" />
        {label}
      </Badge>
    )
  }
  const isAuthFailure = state === 'auth_failure'
  return (
    <Badge
      variant="outline"
      className={cn(
        'gap-1 whitespace-nowrap',
        isAuthFailure
          ? 'border-red-300 text-red-700 dark:border-red-700 dark:text-red-400'
          : 'border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-400',
      )}
      title={detail}
    >
      <AlertTriangle className="h-3 w-3" />
      {label}
    </Badge>
  )
}

function AccountDialog({
  open,
  mode,
  account,
  accounts,
  onOpenChange,
}: {
  open: boolean
  mode: ConnectionMode
  account: AmazonAccount | null
  accounts: AmazonAccount[]
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const [accountName, setAccountName] = useState(account?.account_name || '')
  const [accountType, setAccountType] = useState<AccountType>(account?.account_type || 'seller')
  const [marketplace, setMarketplace] = useState(account?.marketplace_id || '')
  const [spToken, setSpToken] = useState('')
  const [adsToken, setAdsToken] = useState('')
  const [adsClientId, setAdsClientId] = useState('')
  const [adsClientSecret, setAdsClientSecret] = useState('')
  const [selectedAccountId, setSelectedAccountId] = useState(account?.id || 'new')
  const [selectedProfileId, setSelectedProfileId] = useState('')
  const [profiles, setProfiles] = useState<AdvertisingProfile[]>([])

  const selectedMarketplace = marketplaces.find((item) => item.id === marketplace)
  const targetAccount = accounts.find((item) => item.id === selectedAccountId) || account

  const { data: savedApiKeys } = useQuery<ApiKeysResponse>({
    queryKey: ['api-keys'],
    queryFn: () => authApi.getApiKeys(),
  })

  const createMutation = useMutation({
    mutationFn: (data: AccountPayload) => accountsApi.create(data as Partial<AmazonAccount>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      toast({ title: t('accounts.saved') })
      onOpenChange(false)
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('accounts.saveFailed') })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<AccountPayload> }) =>
      accountsApi.update(id, data as Partial<AmazonAccount>),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      toast({ title: t('accounts.saved') })
      onOpenChange(false)
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('accounts.saveFailed') })
    },
  })

  const profilesMutation = useMutation({
    mutationFn: () => accountsApi.listAdvertisingProfiles({
      refresh_token: adsToken || undefined,
      account_id: account?.id,
      marketplace_country: selectedMarketplace?.country || targetAccount?.marketplace_country,
      client_id: adsClientId || undefined,
      client_secret: adsClientSecret || undefined,
    }),
    onSuccess: (items) => {
      setProfiles(items)
      const firstMatch = items.find((profile) =>
        profile.country_code && targetAccount?.marketplace_country &&
        profile.country_code.toUpperCase() === targetAccount.marketplace_country.toUpperCase()
      ) || items[0]
      setSelectedProfileId(firstMatch?.profile_id || '')
      toast({ title: t('accounts.adsProfilesLoaded') })
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast({
        variant: 'destructive',
        title: t('accounts.adsProfilesFailed'),
        description: detail,
      })
    },
  })

  const save = () => {
    if (mode === 'ads') {
      const profile = profiles.find((item) => item.profile_id === selectedProfileId)
      const targetId = selectedAccountId !== 'new' ? selectedAccountId : undefined
      if (targetId) {
        updateMutation.mutate({
          id: targetId,
          data: {
            advertising_refresh_token: adsToken || undefined,
            advertising_profile_id: selectedProfileId || undefined,
          },
        })
        return
      }
      if (!profile || !profile.marketplace_id || !profile.country_code) return
      createMutation.mutate({
        account_name: profile.account_name || t('accounts.adsOnlyAccount'),
        account_type: (profile.account_type === 'vendor' ? 'vendor' : 'seller'),
        marketplace_id: profile.marketplace_id,
        marketplace_country: profile.country_code,
        advertising_refresh_token: adsToken || undefined,
        advertising_profile_id: profile.profile_id,
      })
      return
    }

    if (!selectedMarketplace) return
    const payload: AccountPayload = {
      account_name: accountName,
      account_type: accountType,
      marketplace_id: selectedMarketplace.id,
      marketplace_country: selectedMarketplace.country,
      refresh_token: spToken || undefined,
    }
    if (account) {
      updateMutation.mutate({ id: account.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending
  const title = mode === 'ads'
    ? t('accounts.connectAds')
    : mode === 'sp'
      ? t('accounts.connectSellerCentral')
      : account
        ? t('accounts.editAccount')
        : t('accounts.addAccountManually')

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {mode === 'ads' ? t('accounts.adsFlowDesc') : t('accounts.spFlowDesc')}
          </DialogDescription>
        </DialogHeader>

        {mode !== 'ads' ? (
          <div className="space-y-4">
            {savedApiKeys && !(savedApiKeys.sp_api_client_id && savedApiKeys.has_client_secret) && (
              <Alert variant="warning">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>{t('accounts.spKeysMissingTitle')}</AlertTitle>
                <AlertDescription>
                  {t('accounts.spKeysMissingDesc')}{' '}
                  <Link to="/settings?tab=amazon-api" className="font-medium underline">
                    {t('settings.tabAmazonApi')}
                  </Link>
                </AlertDescription>
              </Alert>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>{t('accounts.dialog.accountName')}</Label>
                <Input value={accountName} onChange={(e) => setAccountName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>{t('accounts.dialog.accountType')}</Label>
                <Select value={accountType} onValueChange={(value: AccountType) => setAccountType(value)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="seller">{t('accounts.dialog.seller')}</SelectItem>
                    <SelectItem value="vendor">{t('accounts.dialog.vendor')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t('accounts.dialog.marketplace')}</Label>
              <Select value={marketplace} onValueChange={setMarketplace}>
                <SelectTrigger><SelectValue placeholder={t('accounts.dialog.selectMarketplace')} /></SelectTrigger>
                <SelectContent>
                  {marketplaces.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {t(item.nameKey)} ({item.country})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{t('accounts.dialog.refreshToken')}</Label>
              <Input
                type="password"
                value={spToken}
                onChange={(e) => setSpToken(e.target.value)}
                placeholder={account?.has_refresh_token ? t('accounts.keepExistingToken') : 'Atzr|...'}
              />
              <p className="text-xs text-muted-foreground">{t('accounts.dialog.refreshTokenHelp')}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <Alert>
              <Megaphone className="h-4 w-4" />
              <AlertTitle>{t('accounts.adsSeparateTitle')}</AlertTitle>
              <AlertDescription>{t('accounts.adsSeparateDesc')}</AlertDescription>
            </Alert>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>{t('accounts.adsRefreshToken')}</Label>
                <Input
                  type="password"
                  value={adsToken}
                  onChange={(e) => setAdsToken(e.target.value)}
                  placeholder={account?.has_advertising_refresh_token ? t('accounts.keepExistingToken') : 'Atzr|...'}
                />
              </div>
              <div className="space-y-2">
                <Label>{t('accounts.dialog.marketplace')}</Label>
                <Select value={marketplace} onValueChange={setMarketplace}>
                  <SelectTrigger><SelectValue placeholder={t('accounts.scanAllRegions')} /></SelectTrigger>
                  <SelectContent>
                    {marketplaces.map((item) => (
                      <SelectItem key={item.id} value={item.id}>
                        {t(item.nameKey)} ({item.country})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>{t('accounts.adsClientId')}</Label>
                <Input value={adsClientId} onChange={(e) => setAdsClientId(e.target.value)} placeholder={t('accounts.optionalIfConfigured')} />
              </div>
              <div className="space-y-2">
                <Label>{t('accounts.adsClientSecret')}</Label>
                <Input type="password" value={adsClientSecret} onChange={(e) => setAdsClientSecret(e.target.value)} placeholder={t('accounts.optionalIfConfigured')} />
              </div>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => profilesMutation.mutate()}
              disabled={profilesMutation.isPending || (!adsToken && !account?.has_advertising_refresh_token)}
            >
              {profilesMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Search className="mr-2 h-4 w-4" />}
              {t('accounts.listAdsProfiles')}
            </Button>

            {profiles.length > 0 && (
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label>{t('accounts.advertisingProfile')}</Label>
                  <Select value={selectedProfileId} onValueChange={setSelectedProfileId}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {profiles.map((profile) => (
                        <SelectItem key={profile.profile_id} value={profile.profile_id}>
                          {profile.account_name || profile.profile_id} - {profile.country_code || t('accounts.unknownMarketplace')}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('accounts.linkToAccount')}</Label>
                  <Select value={selectedAccountId} onValueChange={setSelectedAccountId}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="new">{t('accounts.createAdsOnlyAccount')}</SelectItem>
                      {accounts.map((item) => (
                        <SelectItem key={item.id} value={item.id}>
                          {item.account_name} - {item.marketplace_country}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="button" onClick={save} disabled={isSaving}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function AccountsSection({ embedded = false }: { embedded?: boolean }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [dialogMode, setDialogMode] = useState<ConnectionMode | null>(null)
  const [selectedAccount, setSelectedAccount] = useState<AmazonAccount | null>(null)
  const [detailsAccount, setDetailsAccount] = useState<AmazonAccount | null>(null)
  const [marketplaceFilter, setMarketplaceFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter] = useState<'all' | AccountType>('all')

  const { data: accounts = [], isLoading, isError } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
    // While any account is syncing/backfilling, poll so its status badge
    // resolves from "Syncing" to "Synced" on its own, without a manual refresh.
    refetchInterval: (query) =>
      (query.state.data ?? []).some(
        (a) => a.sync_status === 'syncing' || a.last_backfill_status === 'running',
      ) ? 8000 : false,
  })

  const { data: summary } = useQuery<AccountSummary>({
    queryKey: ['accounts-summary'],
    queryFn: () => accountsApi.getSummary(),
  })

  const syncMutation = useMutation({
    mutationFn: (id: string) => accountsApi.triggerSync(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast({ title: t('accounts.syncStarted') })
    },
    onError: () => toast({ variant: 'destructive', title: t('accounts.syncFailed') }),
  })

  const backfillMutation = useMutation({
    mutationFn: (id: string) => accountsApi.triggerBackfill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      toast({ title: t('accounts.backfill.started'), description: t('accounts.backfill.startedDesc') })
    },
    onError: () => toast({ variant: 'destructive', title: t('accounts.backfill.failed') }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => accountsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      toast({ title: t('accounts.deleted') })
    },
    onError: () => toast({ variant: 'destructive', title: t('accounts.deleteFailed') }),
  })

  const filteredAccounts = useMemo(() => accounts.filter((account) => {
    if (marketplaceFilter !== 'all' && account.marketplace_country !== marketplaceFilter) return false
    if (typeFilter !== 'all' && account.account_type !== typeFilter) return false
    if (statusFilter !== 'all' && connectionState(account) !== statusFilter) return false
    return true
  }), [accounts, marketplaceFilter, statusFilter, typeFilter])

  const marketplaceOptions = Array.from(new Set(accounts.map((account) => account.marketplace_country))).sort()
  const fullConnectionCount = accounts.filter((account) => connectionState(account) === 'connected').length
  const partialConnectionCount = accounts.filter((account) => connectionState(account) === 'partial').length
  const placeholderNamedAccounts = accounts.filter((account) => isPlaceholderAccountName(account.account_name))

  const openDialog = (mode: ConnectionMode, account: AmazonAccount | null = null) => {
    setDetailsAccount(null)
    setSelectedAccount(account)
    setDialogMode(mode)
  }

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>{t('accounts.loadFailed')}</AlertTitle>
        <AlertDescription>{t('accounts.loadFailedDesc')}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          {embedded ? (
            <h2 className="text-2xl font-semibold tracking-tight">{t('accounts.title')}</h2>
          ) : (
            <h1 className="text-3xl font-bold tracking-tight">{t('accounts.title')}</h1>
          )}
          <p className="text-muted-foreground">{t('accounts.subtitle')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => openDialog('sp')}>
            <Store className="mr-2 h-4 w-4" />
            {t('accounts.connectSellerCentral')}
          </Button>
          <Button variant="outline" onClick={() => openDialog('ads')}>
            <Megaphone className="mr-2 h-4 w-4" />
            {t('accounts.connectAds')}
          </Button>
          <Button variant="outline" onClick={() => openDialog('manual')}>
            <Plus className="mr-2 h-4 w-4" />
            {t('accounts.addAccountManually')}
          </Button>
        </div>
      </div>

      {!embedded && (
        <Alert>
          <Link2 className="h-4 w-4" />
          <AlertTitle>{t('accounts.separateConnectionsTitle')}</AlertTitle>
          <AlertDescription>{t('accounts.separateConnectionsDesc')}</AlertDescription>
        </Alert>
      )}

      {placeholderNamedAccounts.length > 0 && (
        <Alert variant="warning">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('accounts.placeholderNameAlertTitle')}</AlertTitle>
          <AlertDescription>
            {t('accounts.placeholderNameAlertDesc')}
            {' '}
            <span className="font-medium">
              {placeholderNamedAccounts.map((account) => account.account_name).join(', ')}
            </span>
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-3 md:grid-cols-4">
        <Card><CardContent className="pt-5"><div className="text-2xl font-bold">{summary?.total_accounts || 0}</div><p className="text-sm text-muted-foreground">{t('accounts.totalAccounts')}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-2xl font-bold text-emerald-600">{fullConnectionCount}</div><p className="text-sm text-muted-foreground">{t('accounts.fullConnected')}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-2xl font-bold text-amber-600">{partialConnectionCount}</div><p className="text-sm text-muted-foreground">{t('accounts.partialConnected')}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><div className="text-2xl font-bold text-red-600">{summary?.error_accounts || 0}</div><p className="text-sm text-muted-foreground">{t('accounts.errors')}</p></CardContent></Card>
      </div>

      <div className="flex flex-col gap-3 md:flex-row">
        <Select value={marketplaceFilter} onValueChange={setMarketplaceFilter}>
          <SelectTrigger className="md:w-[190px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('accounts.allMarketplaces')}</SelectItem>
            {marketplaceOptions.map((country) => <SelectItem key={country} value={country}>{country}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={(value: StatusFilter) => setStatusFilter(value)}>
          <SelectTrigger className="md:w-[190px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('accounts.allStatuses')}</SelectItem>
            <SelectItem value="connected">{t('accounts.fullConnected')}</SelectItem>
            <SelectItem value="partial">{t('accounts.partialConnected')}</SelectItem>
            <SelectItem value="missing">{t('accounts.missingCredentials')}</SelectItem>
            <SelectItem value="error">{t('accounts.syncFailedStatus')}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={typeFilter} onValueChange={(value: 'all' | AccountType) => setTypeFilter(value)}>
          <SelectTrigger className="md:w-[170px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t('accounts.allTypes')}</SelectItem>
            <SelectItem value="seller">{t('accounts.dialog.seller')}</SelectItem>
            <SelectItem value="vendor">{t('accounts.dialog.vendor')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {accounts.length === 0 ? (
        <div className="rounded-lg border border-dashed p-10 text-center">
          <Store className="mx-auto h-10 w-10 text-muted-foreground" />
          <h3 className="mt-4 text-lg font-semibold">{t('accounts.emptyTitle')}</h3>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">{t('accounts.emptyDesc')}</p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <Button onClick={() => openDialog('sp')}><Store className="mr-2 h-4 w-4" />{t('accounts.connectSellerCentral')}</Button>
            <Button variant="outline" onClick={() => openDialog('ads')}><Megaphone className="mr-2 h-4 w-4" />{t('accounts.connectAds')}</Button>
          </div>
        </div>
      ) : (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('accounts.connectedAccounts')}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('accounts.accountName')}</TableHead>
                  <TableHead>{t('accounts.marketplace')}</TableHead>
                  <TableHead>{t('accounts.accountType')}</TableHead>
                  <TableHead>{t('accounts.spApiStatus')}</TableHead>
                  <TableHead>{t('accounts.adsStatus')}</TableHead>
                  <TableHead>{t('accounts.advertisingProfile')}</TableHead>
                  <TableHead>{t('accounts.lastSync')}</TableHead>
                  <TableHead>{t('accounts.syncStatus')}</TableHead>
                  <TableHead>{t('accounts.backfill.column')}</TableHead>
                  <TableHead className="text-right">{t('accounts.actions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredAccounts.map((account) => {
                  const isPlaceholder = isPlaceholderAccountName(account.account_name)
                  return (
                  <TableRow
                    key={account.id}
                    className={cn(
                      'cursor-pointer',
                      isPlaceholder && 'bg-amber-50/40 dark:bg-amber-950/20',
                    )}
                    onClick={() => setDetailsAccount(account)}
                  >
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        <span>{account.account_name}</span>
                        {isPlaceholder && (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              openDialog('manual', account)
                            }}
                            className="inline-flex"
                            title={t('accounts.placeholderNameTooltip')}
                          >
                            <Badge
                              variant="outline"
                              className="gap-1 whitespace-nowrap border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-400"
                            >
                              <AlertTriangle className="h-3 w-3" />
                              {t('accounts.placeholderNameBadge')}
                            </Badge>
                          </button>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{account.marketplace_country}</TableCell>
                    <TableCell><Badge variant="outline">{account.account_type}</Badge></TableCell>
                    <TableCell><CredentialBadge connected={account.has_refresh_token} label={account.has_refresh_token ? t('accounts.connected') : t('accounts.missing')} /></TableCell>
                    <TableCell><AdsStateBadge account={account} /></TableCell>
                    <TableCell className="font-mono text-xs">{account.advertising_profile_id || '-'}</TableCell>
                    <TableCell>{account.last_sync_at ? formatDate(account.last_sync_at) : t('common.never')}</TableCell>
                    <TableCell><StatusBadge status={account.sync_status} /></TableCell>
                    <TableCell><BackfillBadge account={account} /></TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1" onClick={(event) => event.stopPropagation()}>
                        <Button variant="ghost" size="icon" onClick={() => openDialog('manual', account)} aria-label={t('common.edit')}><Edit className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" onClick={() => openDialog('sp', account)} aria-label={t('accounts.reconnectSp')}><KeyRound className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" onClick={() => openDialog('ads', account)} aria-label={t('accounts.reconnectAds')}><Megaphone className="h-4 w-4" /></Button>
                        <Button variant="ghost" size="icon" onClick={() => syncMutation.mutate(account.id)} disabled={syncMutation.isPending || account.sync_status === 'syncing'} aria-label={t('accounts.sync')}><RefreshCw className="h-4 w-4" /></Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            if (window.confirm(t('accounts.backfill.confirm'))) backfillMutation.mutate(account.id)
                          }}
                          disabled={!account.has_refresh_token || backfillMutation.isPending || account.sync_status === 'syncing' || account.last_backfill_status === 'running'}
                          aria-label={t('accounts.backfill.action')}
                          title={t('accounts.backfill.action')}
                        >
                          <History className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => setDetailsAccount(account)} aria-label={t('accounts.viewDetails')}><Eye className="h-4 w-4" /></Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => {
                            if (window.confirm(t('accounts.deleteConfirm'))) deleteMutation.mutate(account.id)
                          }}
                          aria-label={t('common.delete')}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog open={!!detailsAccount} onOpenChange={(open) => !open && setDetailsAccount(null)}>
        <DialogContent className="sm:max-w-xl">
          {detailsAccount && (
            <>
              <DialogHeader>
                <DialogTitle>{detailsAccount.account_name}</DialogTitle>
                <DialogDescription>{detailsAccount.marketplace_country} - {detailsAccount.account_type}</DialogDescription>
              </DialogHeader>
              <div className="grid gap-3 text-sm">
                <div className="flex justify-between gap-4"><span className="text-muted-foreground">{t('accounts.spApiStatus')}</span><CredentialBadge connected={detailsAccount.has_refresh_token} label={detailsAccount.has_refresh_token ? t('accounts.connected') : t('accounts.missing')} /></div>
                <div className="flex justify-between gap-4"><span className="text-muted-foreground">{t('accounts.adsStatus')}</span><AdsStateBadge account={detailsAccount} /></div>
                {detailsAccount.ads_connection_detail && resolveAdsState(detailsAccount) !== 'ok' && (
                  <p className="text-xs text-muted-foreground">{detailsAccount.ads_connection_detail}</p>
                )}
                <div className="flex justify-between gap-4"><span className="text-muted-foreground">{t('accounts.advertisingProfile')}</span><span className="font-mono">{detailsAccount.advertising_profile_id || '-'}</span></div>
                <div className="flex justify-between gap-4"><span className="text-muted-foreground">{t('accounts.lastSync')}</span><span>{detailsAccount.last_sync_at ? formatDate(detailsAccount.last_sync_at) : t('common.never')}</span></div>
                <div className="flex justify-between gap-4"><span className="text-muted-foreground">{t('accounts.syncStatus')}</span><StatusBadge status={detailsAccount.sync_status} /></div>
                <div className="flex justify-between gap-4"><span className="text-muted-foreground">{t('accounts.backfill.column')}</span><BackfillBadge account={detailsAccount} /></div>
                {detailsAccount.last_backfill_range_start && detailsAccount.last_backfill_range_end && (
                  <div className="flex justify-between gap-4">
                    <span className="text-muted-foreground">{t('accounts.backfill.range')}</span>
                    <span>
                      {formatDate(detailsAccount.last_backfill_range_start)} → {formatDate(detailsAccount.last_backfill_range_end)}
                      {detailsAccount.last_backfill_records != null && ` (${detailsAccount.last_backfill_records} ${t('accounts.backfill.records')})`}
                    </span>
                  </div>
                )}
                {detailsAccount.last_backfill_error && (
                  <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>{t('accounts.backfill.error')}</AlertTitle>
                    <AlertDescription>{detailsAccount.last_backfill_error}</AlertDescription>
                  </Alert>
                )}
                {detailsAccount.sync_error_message && (
                  <Alert variant={detailsAccount.sync_error_kind === 'warning' ? 'warning' : 'destructive'}>
                    {detailsAccount.sync_error_kind === 'warning' ? <AlertTriangle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                    <AlertTitle>{detailsAccount.sync_error_kind === 'warning' ? t('alerts.severity.warning') : t('accounts.lastError')}</AlertTitle>
                    <AlertDescription>{detailsAccount.sync_error_message}</AlertDescription>
                  </Alert>
                )}
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => openDialog('sp', detailsAccount)}>{t('accounts.reconnectSp')}</Button>
                <Button variant="outline" onClick={() => openDialog('ads', detailsAccount)}>{t('accounts.reconnectAds')}</Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    if (window.confirm(t('accounts.backfill.confirm'))) backfillMutation.mutate(detailsAccount.id)
                  }}
                  disabled={!detailsAccount.has_refresh_token || backfillMutation.isPending || detailsAccount.sync_status === 'syncing' || detailsAccount.last_backfill_status === 'running'}
                >
                  <History className="mr-2 h-4 w-4" />
                  {t('accounts.backfill.action')}
                </Button>
                <Button onClick={() => syncMutation.mutate(detailsAccount.id)}>{t('accounts.sync')}</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <AccountDialog
        key={`${dialogMode || 'closed'}-${selectedAccount?.id || 'new'}`}
        open={!!dialogMode}
        mode={dialogMode || 'manual'}
        account={selectedAccount}
        accounts={accounts}
        onOpenChange={(open) => {
          if (!open) {
            setDialogMode(null)
            setSelectedAccount(null)
          }
        }}
      />
    </div>
  )
}
