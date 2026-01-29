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
import { accountsApi } from '@/services/api'
import { formatDate } from '@/lib/utils'
import type { AmazonAccount, AccountSummary, SyncStatus } from '@/types'

const marketplaces = [
  { id: 'A1PA6795UKMFR9', country: 'DE', name: 'Germany' },
  { id: 'APJ6JRA9NG5V4', country: 'IT', name: 'Italy' },
  { id: 'A1F83G8C2ARO7P', country: 'UK', name: 'United Kingdom' },
  { id: 'A13V1IB3VIYZZH', country: 'FR', name: 'France' },
  { id: 'A1RKKUPIHCS9HS', country: 'ES', name: 'Spain' },
]

function StatusBadge({ status }: { status: SyncStatus }) {
  switch (status) {
    case 'success':
      return (
        <Badge variant="success" className="gap-1">
          <Check className="h-3 w-3" /> Synced
        </Badge>
      )
    case 'syncing':
      return (
        <Badge variant="secondary" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" /> Syncing
        </Badge>
      )
    case 'error':
      return (
        <Badge variant="destructive" className="gap-1">
          <AlertCircle className="h-3 w-3" /> Error
        </Badge>
      )
    default:
      return (
        <Badge variant="outline" className="gap-1">
          <Clock className="h-3 w-3" /> Pending
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
  const [accountName, setAccountName] = useState('')
  const [accountType, setAccountType] = useState<'seller' | 'vendor'>('seller')
  const [marketplace, setMarketplace] = useState('')
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')

  const queryClient = useQueryClient()
  const { toast } = useToast()

  const createMutation = useMutation({
    mutationFn: (data: Partial<AmazonAccount>) => accountsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      toast({ title: 'Account added successfully' })
      onOpenChange(false)
      resetForm()
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: 'Failed to add account',
        description: 'Please check your credentials and try again.',
      })
    },
  })

  const resetForm = () => {
    setAccountName('')
    setAccountType('seller')
    setMarketplace('')
    setLoginEmail('')
    setLoginPassword('')
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
      login_email: loginEmail,
      login_password: loginPassword,
    } as Partial<AmazonAccount>)
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Add Amazon Account</CardTitle>
          <CardDescription>
            Connect a new Amazon Seller or Vendor account
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="accountName">Account Name</Label>
              <Input
                id="accountName"
                placeholder="My Store"
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="accountType">Account Type</Label>
              <Select value={accountType} onValueChange={(v: 'seller' | 'vendor') => setAccountType(v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="seller">Seller Central</SelectItem>
                  <SelectItem value="vendor">Vendor Central</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="marketplace">Marketplace</Label>
              <Select value={marketplace} onValueChange={setMarketplace}>
                <SelectTrigger>
                  <SelectValue placeholder="Select marketplace" />
                </SelectTrigger>
                <SelectContent>
                  {marketplaces.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.name} ({m.country})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="loginEmail">Login Email</Label>
              <Input
                id="loginEmail"
                type="email"
                placeholder="email@example.com"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="loginPassword">Login Password</Label>
              <Input
                id="loginPassword"
                type="password"
                placeholder="Account password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
              />
            </div>
          </CardContent>
          <div className="flex justify-end gap-2 p-6 pt-0">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add Account
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
      toast({ title: 'Sync started' })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: 'Failed to start sync',
      })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => accountsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      toast({ title: 'Account deleted' })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: 'Failed to delete account',
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
          <h1 className="text-3xl font-bold tracking-tight">Amazon Accounts</h1>
          <p className="text-muted-foreground">
            Manage your connected Amazon Seller and Vendor accounts
          </p>
        </div>
        <Button onClick={() => setShowAddDialog(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Account
        </Button>
      </div>

      {/* Summary */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{summary?.total_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">Total Accounts</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-green-600">{summary?.active_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">Active</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-blue-600">{summary?.syncing_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">Syncing</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold text-red-600">{summary?.error_accounts || 0}</div>
            <p className="text-sm text-muted-foreground">Errors</p>
          </CardContent>
        </Card>
      </div>

      {/* Account List */}
      <div className="space-y-4">
        {accounts?.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center">
              <p className="text-muted-foreground">No accounts connected yet.</p>
              <Button className="mt-4" onClick={() => setShowAddDialog(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Your First Account
              </Button>
            </CardContent>
          </Card>
        ) : (
          accounts?.map((account) => (
            <Card key={account.id}>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <h3 className="font-semibold text-lg">{account.account_name}</h3>
                      <StatusBadge status={account.sync_status} />
                      <Badge variant="outline">{account.account_type}</Badge>
                      <Badge variant="secondary">{account.marketplace_country}</Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Last synced: {account.last_sync_at ? formatDate(account.last_sync_at) : 'Never'}
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
                      Sync
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm('Are you sure you want to delete this account?')) {
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
