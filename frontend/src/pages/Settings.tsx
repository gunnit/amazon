import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { User, Bell, Shield, Database, Key, Loader2, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/store/authStore'
import { useDemoStore } from '@/store/demoStore'
import { authApi } from '@/services/api'
import type { ApiKeysResponse } from '@/types'

export default function Settings() {
  const { user, organization } = useAuthStore()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const { mockDataEnabled, setMockDataEnabled } = useDemoStore()
  const [isSaving, setIsSaving] = useState(false)

  const [profile, setProfile] = useState({
    fullName: user?.full_name || '',
    email: user?.email || '',
  })

  const [notifications, setNotifications] = useState({
    dailyDigest: true,
    alertEmails: true,
    syncNotifications: false,
  })

  // API Keys state
  const [apiKeys, setApiKeys] = useState({
    sp_api_client_id: '',
    sp_api_client_secret: '',
    sp_api_aws_access_key: '',
    sp_api_aws_secret_key: '',
    sp_api_role_arn: '',
  })

  const { data: savedApiKeys } = useQuery<ApiKeysResponse>({
    queryKey: ['api-keys'],
    queryFn: () => authApi.getApiKeys(),
  })

  const apiKeysMutation = useMutation({
    mutationFn: (data: typeof apiKeys) => {
      const payload: Record<string, string> = {}
      if (data.sp_api_client_id) payload.sp_api_client_id = data.sp_api_client_id
      if (data.sp_api_client_secret) payload.sp_api_client_secret = data.sp_api_client_secret
      if (data.sp_api_aws_access_key) payload.sp_api_aws_access_key = data.sp_api_aws_access_key
      if (data.sp_api_aws_secret_key) payload.sp_api_aws_secret_key = data.sp_api_aws_secret_key
      if (data.sp_api_role_arn) payload.sp_api_role_arn = data.sp_api_role_arn
      return authApi.updateApiKeys(payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      setApiKeys({
        sp_api_client_id: '',
        sp_api_client_secret: '',
        sp_api_aws_access_key: '',
        sp_api_aws_secret_key: '',
        sp_api_role_arn: '',
      })
      toast({ title: 'API keys saved successfully' })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: 'Failed to save API keys',
      })
    },
  })

  const handleSaveProfile = async () => {
    setIsSaving(true)
    try {
      const updatedUser = await authApi.updateProfile({
        full_name: profile.fullName,
        email: profile.email,
      })
      useAuthStore.getState().setUser(updatedUser)
      toast({ title: 'Profile updated successfully' })
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to update profile'
      toast({
        variant: 'destructive',
        title: message,
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleSaveNotifications = async () => {
    setIsSaving(true)
    try {
      await new Promise((resolve) => setTimeout(resolve, 1000))
      toast({ title: 'Notification settings saved' })
    } catch {
      toast({
        variant: 'destructive',
        title: 'Failed to save settings',
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleMockToggle = (enabled: boolean) => {
    setMockDataEnabled(enabled)
    queryClient.clear()
    toast({
      title: enabled ? 'Demo data enabled' : 'Demo data disabled',
      description: enabled
        ? 'All screens will show simulated data for demonstrations.'
        : 'Live data is enabled again.',
    })
  }

  const handleSaveApiKeys = (e: React.FormEvent) => {
    e.preventDefault()
    apiKeysMutation.mutate(apiKeys)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account and application preferences
        </p>
      </div>

      <Tabs defaultValue="profile" className="space-y-4">
        <TabsList>
          <TabsTrigger value="profile" className="gap-2">
            <User className="h-4 w-4" /> Profile
          </TabsTrigger>
          <TabsTrigger value="amazon-api" className="gap-2">
            <Key className="h-4 w-4" /> Amazon API
          </TabsTrigger>
          <TabsTrigger value="notifications" className="gap-2">
            <Bell className="h-4 w-4" /> Notifications
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-2">
            <Shield className="h-4 w-4" /> Security
          </TabsTrigger>
          <TabsTrigger value="data" className="gap-2">
            <Database className="h-4 w-4" /> Data
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle>Profile Information</CardTitle>
              <CardDescription>
                Update your personal information and email address
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="fullName">Full Name</Label>
                <Input
                  id="fullName"
                  value={profile.fullName}
                  onChange={(e) =>
                    setProfile({ ...profile, fullName: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={profile.email}
                  onChange={(e) =>
                    setProfile({ ...profile, email: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label>Organization</Label>
                <Input value={organization?.name || ''} disabled />
                <p className="text-xs text-muted-foreground">
                  Contact support to change your organization
                </p>
              </div>
              <Button onClick={handleSaveProfile} disabled={isSaving}>
                {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save Changes
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="amazon-api">
          <Card>
            <CardHeader>
              <CardTitle>Amazon SP-API Credentials</CardTitle>
              <CardDescription>
                Configure your Amazon Selling Partner API credentials. These are used
                to connect to your Amazon accounts and pull data automatically.
                You can find these in your{' '}
                <a
                  href="https://sellercentral.amazon.com/apps/authorize/consent"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline text-primary"
                >
                  Seller Central Developer Console
                </a>.
              </CardDescription>
            </CardHeader>
            <form onSubmit={handleSaveApiKeys}>
              <CardContent className="space-y-5">
                {/* Current status */}
                {savedApiKeys && (savedApiKeys.sp_api_client_id || savedApiKeys.has_client_secret) && (
                  <div className="rounded-md border bg-muted/30 p-4 space-y-2">
                    <p className="text-sm font-medium flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      Credentials configured
                    </p>
                    <div className="grid gap-1 text-xs text-muted-foreground">
                      {savedApiKeys.sp_api_client_id && (
                        <p>Client ID: <span className="font-mono">{savedApiKeys.sp_api_client_id}</span></p>
                      )}
                      {savedApiKeys.has_client_secret && (
                        <p>Client Secret: <span className="font-mono">configured</span></p>
                      )}
                      {savedApiKeys.sp_api_aws_access_key && (
                        <p>AWS Access Key: <span className="font-mono">{savedApiKeys.sp_api_aws_access_key}</span></p>
                      )}
                      {savedApiKeys.has_aws_secret_key && (
                        <p>AWS Secret Key: <span className="font-mono">configured</span></p>
                      )}
                      {savedApiKeys.sp_api_role_arn && (
                        <p>Role ARN: <span className="font-mono">{savedApiKeys.sp_api_role_arn}</span></p>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Fill in fields below only to update values. Leave empty to keep current.
                    </p>
                  </div>
                )}

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="clientId">SP-API Client ID</Label>
                    <Input
                      id="clientId"
                      value={apiKeys.sp_api_client_id}
                      onChange={(e) => setApiKeys({ ...apiKeys, sp_api_client_id: e.target.value })}
                      placeholder={savedApiKeys?.sp_api_client_id || 'amzn1.application-oa2-client.xxx'}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="clientSecret">SP-API Client Secret</Label>
                    <Input
                      id="clientSecret"
                      type="password"
                      value={apiKeys.sp_api_client_secret}
                      onChange={(e) => setApiKeys({ ...apiKeys, sp_api_client_secret: e.target.value })}
                      placeholder={savedApiKeys?.has_client_secret ? '••••••••' : 'Your client secret'}
                    />
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="awsAccessKey">AWS Access Key</Label>
                    <Input
                      id="awsAccessKey"
                      value={apiKeys.sp_api_aws_access_key}
                      onChange={(e) => setApiKeys({ ...apiKeys, sp_api_aws_access_key: e.target.value })}
                      placeholder={savedApiKeys?.sp_api_aws_access_key || 'AKIA...'}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="awsSecretKey">AWS Secret Key</Label>
                    <Input
                      id="awsSecretKey"
                      type="password"
                      value={apiKeys.sp_api_aws_secret_key}
                      onChange={(e) => setApiKeys({ ...apiKeys, sp_api_aws_secret_key: e.target.value })}
                      placeholder={savedApiKeys?.has_aws_secret_key ? '••••••••' : 'Your AWS secret key'}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="roleArn">IAM Role ARN</Label>
                  <Input
                    id="roleArn"
                    value={apiKeys.sp_api_role_arn}
                    onChange={(e) => setApiKeys({ ...apiKeys, sp_api_role_arn: e.target.value })}
                    placeholder={savedApiKeys?.sp_api_role_arn || 'arn:aws:iam::123456789:role/sp-api'}
                  />
                  <p className="text-xs text-muted-foreground">
                    The IAM role ARN that grants access to the SP-API. Optional if using user-level credentials.
                  </p>
                </div>

                <Button type="submit" disabled={apiKeysMutation.isPending}>
                  {apiKeysMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Save API Keys
                </Button>
              </CardContent>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <CardTitle>Notification Preferences</CardTitle>
              <CardDescription>
                Choose what notifications you want to receive
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Daily Digest</p>
                  <p className="text-sm text-muted-foreground">
                    Receive a daily summary of your account performance
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={notifications.dailyDigest}
                  onChange={(e) =>
                    setNotifications({
                      ...notifications,
                      dailyDigest: e.target.checked,
                    })
                  }
                  className="h-4 w-4"
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Alert Emails</p>
                  <p className="text-sm text-muted-foreground">
                    Get notified when alerts are triggered
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={notifications.alertEmails}
                  onChange={(e) =>
                    setNotifications({
                      ...notifications,
                      alertEmails: e.target.checked,
                    })
                  }
                  className="h-4 w-4"
                />
              </div>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Sync Notifications</p>
                  <p className="text-sm text-muted-foreground">
                    Get notified when data syncs complete or fail
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={notifications.syncNotifications}
                  onChange={(e) =>
                    setNotifications({
                      ...notifications,
                      syncNotifications: e.target.checked,
                    })
                  }
                  className="h-4 w-4"
                />
              </div>
              <Button onClick={handleSaveNotifications} disabled={isSaving}>
                {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Save Preferences
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle>Security Settings</CardTitle>
              <CardDescription>
                Manage your password and security preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="currentPassword">Current Password</Label>
                <Input id="currentPassword" type="password" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="newPassword">New Password</Label>
                <Input id="newPassword" type="password" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm New Password</Label>
                <Input id="confirmPassword" type="password" />
              </div>
              <Button>Change Password</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="data">
          <Card>
            <CardHeader>
              <CardTitle>Data Management</CardTitle>
              <CardDescription>
                Manage your data and export options
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-medium">Demo Data Mode</h3>
                    <p className="text-sm text-muted-foreground">
                      Use simulated data across the app for demos. No live data will be requested.
                    </p>
                  </div>
                  <input
                    type="checkbox"
                    checked={mockDataEnabled}
                    onChange={(e) => handleMockToggle(e.target.checked)}
                    className="h-4 w-4"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  When disabled, the app will use your real Amazon SP-API credentials to fetch data.
                </p>
              </div>
              <div className="space-y-2">
                <h3 className="font-medium">Data Retention</h3>
                <p className="text-sm text-muted-foreground">
                  Your data is retained for 24 months. Historical data beyond
                  Amazon's limits is preserved for analysis.
                </p>
              </div>
              <div className="space-y-2">
                <h3 className="font-medium">Export All Data</h3>
                <p className="text-sm text-muted-foreground">
                  Download a complete export of all your account data.
                </p>
                <Button variant="outline">Request Data Export</Button>
              </div>
              <div className="space-y-2 pt-4 border-t">
                <h3 className="font-medium text-destructive">Danger Zone</h3>
                <p className="text-sm text-muted-foreground">
                  Permanently delete your account and all associated data.
                </p>
                <Button variant="destructive">Delete Account</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
