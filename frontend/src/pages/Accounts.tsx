import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  RefreshCw,
  Check,
  AlertCircle,
  Clock,
  Loader2,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  KeyRound,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { accountsApi, authApi } from '@/services/api'
import { formatDate } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import { Link } from 'react-router-dom'
import type { AmazonAccount, AccountSummary, SyncStatus, ApiKeysResponse } from '@/types'

const marketplaces = [
  { id: 'A1PA6795UKMFR9', country: 'DE', nameKey: 'marketplace.DE' },
  { id: 'APJ6JRA9NG5V4', country: 'IT', nameKey: 'marketplace.IT' },
  { id: 'A1F83G8C2ARO7P', country: 'UK', nameKey: 'marketplace.UK' },
  { id: 'A13V1IB3VIYZZH', country: 'FR', nameKey: 'marketplace.FR' },
  { id: 'A1RKKUPIHCS9HS', country: 'ES', nameKey: 'marketplace.ES' },
]

function StatusBadge({ status }: { status: SyncStatus }) {
  const { t } = useTranslation()
  switch (status) {
    case 'success':
      return (
        <Badge variant="success" className="gap-1">
          <Check className="h-3 w-3" /> {t('accounts.status.synced')}
        </Badge>
      )
    case 'syncing':
      return (
        <Badge variant="secondary" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" /> {t('accounts.status.syncing')}
        </Badge>
      )
    case 'error':
      return (
        <Badge variant="destructive" className="gap-1">
          <AlertCircle className="h-3 w-3" /> {t('accounts.status.error')}
        </Badge>
      )
    default:
      return (
        <Badge variant="outline" className="gap-1">
          <Clock className="h-3 w-3" /> {t('accounts.status.pending')}
        </Badge>
      )
  }
}

function AddAccountDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useTranslation()
  const [accountName, setAccountName] = useState('')
  const [accountType, setAccountType] = useState<'seller' | 'vendor'>('seller')
  const [marketplace, setMarketplace] = useState('')
  const [refreshToken, setRefreshToken] = useState('')

  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: savedApiKeys } = useQuery<ApiKeysResponse>({
    queryKey: ['api-keys'],
    queryFn: () => authApi.getApiKeys(),
  })

  const hasOrgApiKeys = !!(savedApiKeys?.sp_api_client_id || savedApiKeys?.has_client_secret)

  const createMutation = useMutation({
    mutationFn: (data: Partial<AmazonAccount>) => accountsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      toast({ title: t('accounts.addedSuccess') })
      onOpenChange(false)
      resetForm()
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: t('accounts.addedFailed'),
        description: t('accounts.addedFailedDesc'),
      })
    },
  })

  const resetForm = () => {
    setAccountName('')
    setAccountType('seller')
    setMarketplace('')
    setRefreshToken('')
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const selectedMarketplace = marketplaces.find((m) => m.id === marketplace)
    if (!selectedMarketplace) return

    createMutation.mutate({
      account_name: accountName,
      account_type: accountType,
      marketplace_id: marketplace,
      marketplace_country: selectedMarketplace.country,
      refresh_token: refreshToken || undefined,
    } as Partial<AmazonAccount>)
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t('accounts.dialog.title')}</CardTitle>
          <CardDescription>
            {t('accounts.dialog.subtitle')}
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {/* API key status banner */}
            {hasOrgApiKeys ? (
              <div className="flex items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-300">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                {t('accounts.dialog.apiKeysConfigured')}
              </div>
            ) : (
              <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>
                  {t('accounts.dialog.apiKeysMissing')}{' '}
                  <Link to="/settings" className="underline font-medium" onClick={() => onOpenChange(false)}>
                    {t('nav.settings')}
                  </Link>
                </span>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="accountName">{t('accounts.dialog.accountName')}</Label>
              <Input
                id="accountName"
                placeholder={t('accounts.dialog.accountNamePlaceholder')}
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="accountType">{t('accounts.dialog.accountType')}</Label>
              <Select value={accountType} onValueChange={(v: 'seller' | 'vendor') => setAccountType(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="seller">{t('accounts.dialog.seller')}</SelectItem>
                  <SelectItem value="vendor">{t('accounts.dialog.vendor')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="marketplace">{t('accounts.dialog.marketplace')}</Label>
              <Select value={marketplace} onValueChange={setMarketplace}>
                <SelectTrigger>
                  <SelectValue placeholder={t('accounts.dialog.selectMarketplace')} />
                </SelectTrigger>
                <SelectContent>
                  {marketplaces.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {t(m.nameKey)} ({m.country})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="refreshToken">{t('accounts.dialog.refreshToken')}</Label>
              <Input
                id="refreshToken"
                type="password"
                placeholder={t('accounts.dialog.refreshTokenPlaceholder')}
                value={refreshToken}
                onChange={(e) => setRefreshToken(e.target.value)}
                required
              />
              <p className="text-xs text-muted-foreground">
                {t('accounts.dialog.refreshTokenHelp')}
              </p>
            </div>
          </CardContent>
          <div className="flex justify-end gap-2 p-6 pt-0">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('accounts.addAccount')}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}

export default function Accounts() {
  const [showAddDialog, setShowAddDialog] = useState(false)
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  const { data: accounts, isLoading } = useQuery<AmazonAccount[]>({
    queryKey: ['accounts'],
    queryFn: () => accountsApi.list(),
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
    onError: () => {
      toast({
        variant: 'destructive',
        title: t('accounts.syncFailed'),
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => accountsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      toast({ title: t('accounts.deleted') })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: t('accounts.deleteFailed'),
      })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t('accounts.title')}</h1>
          <p className="text-muted-foreground">
            {t('accounts.subtitle')}
          </p>
        </div>
        <Button onClick={() => setShowAddDialog(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t('accounts.addAccount')}
        </Button>
      </div>

      {/* Summary */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{summary?.total_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">{t('accounts.totalAccounts')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-green-600">{summary?.active_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">{t('accounts.active')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-blue-600">{summary?.syncing_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">{t('accounts.syncing')}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-red-600">{summary?.error_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">{t('accounts.errors')}</p>
          </CardContent>
        </Card>
      </div>

      {/* Account List */}
      <div className="space-y-4">
        {accounts?.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="text-muted-foreground">{t('accounts.noAccounts')}</p>
              <Button className="mt-4" onClick={() => setShowAddDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                {t('accounts.addFirstAccount')}
              </Button>
            </CardContent>
          </Card>
        ) : (
          accounts?.map((account) => (
            <Card key={account.id}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h3 className="font-semibold text-lg">{account.account_name}</h3>
                      <StatusBadge status={account.sync_status} />
                      <Badge variant="outline">{account.account_type}</Badge>
                      <Badge variant="secondary">{account.marketplace_country}</Badge>
                      {account.has_refresh_token ? (
                        <Badge variant="outline" className="gap-1 border-emerald-300 text-emerald-700 dark:border-emerald-700 dark:text-emerald-400">
                          <KeyRound className="h-3 w-3" /> {t('accounts.credentialsOk')}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="gap-1 border-amber-300 text-amber-700 dark:border-amber-700 dark:text-amber-400">
                          <AlertTriangle className="h-3 w-3" /> {t('accounts.missingRefreshToken')}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {t('accounts.lastSynced')} {account.last_sync_at ? formatDate(account.last_sync_at) : t('common.never')}
                    </p>
                    {account.sync_error_message && (
                      <p className="text-sm text-destructive">{account.sync_error_message}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => syncMutation.mutate(account.id)}
                      disabled={syncMutation.isPending || account.sync_status === 'syncing'}
                    >
                      <RefreshCw className="mr-2 h-4 w-4" />
                      {t('accounts.sync')}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm(t('accounts.deleteConfirm'))) {
                          deleteMutation.mutate(account.id)
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      <AddAccountDialog open={showAddDialog} onOpenChange={setShowAddDialog} />
    </div>
  )
}
