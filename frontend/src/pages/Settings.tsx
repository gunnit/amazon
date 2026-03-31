import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { User, Bell, Shield, Database, Loader2, CheckCircle2, Globe, AlertTriangle, Trash2, Store, Key } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useToast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/store/authStore'
import { authApi, exportsApi } from '@/services/api'
import { useTranslation } from '@/i18n'
import { AccountsSection } from '@/components/settings/AccountsSection'
import type { Language } from '@/store/languageStore'
import type { ApiKeysResponse } from '@/types'

export default function Settings() {
  const { user, organization } = useAuthStore()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [isSaving, setIsSaving] = useState(false)
  const { t, language, setLanguage } = useTranslation()
  const activeTab = searchParams.get('tab') || 'profile'

  const [profile, setProfile] = useState({
    fullName: user?.full_name || '',
    email: user?.email || '',
  })

  const [notifications, setNotifications] = useState({
    dailyDigest: true,
    alertEmails: true,
    syncNotifications: false,
  })

  const [passwords, setPasswords] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })

  // Load notification preferences from server
  const { data: savedNotifications } = useQuery({
    queryKey: ['notification-preferences'],
    queryFn: () => authApi.getNotificationPreferences(),
  })

  useEffect(() => {
    if (savedNotifications) {
      setNotifications({
        dailyDigest: savedNotifications.daily_digest,
        alertEmails: savedNotifications.alert_emails,
        syncNotifications: savedNotifications.sync_notifications,
      })
    }
  }, [savedNotifications])

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
      toast({ title: t('settings.apiKeysSaved') })
    },
    onError: () => {
      toast({
        variant: 'destructive',
        title: t('settings.apiKeysFailed'),
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
      toast({ title: t('settings.profileUpdated') })
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('settings.profileFailed')
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
      await authApi.updateNotificationPreferences({
        daily_digest: notifications.dailyDigest,
        alert_emails: notifications.alertEmails,
        sync_notifications: notifications.syncNotifications,
      })
      queryClient.invalidateQueries({ queryKey: ['notification-preferences'] })
      toast({ title: t('settings.notifSaved') })
    } catch {
      toast({
        variant: 'destructive',
        title: t('settings.notifFailed'),
      })
    } finally {
      setIsSaving(false)
    }
  }

  const handleChangePassword = async () => {
    if (passwords.newPassword !== passwords.confirmPassword) {
      toast({ variant: 'destructive', title: t('settings.passwordsMismatch') })
      return
    }
    if (passwords.newPassword.length < 8) {
      toast({ variant: 'destructive', title: t('settings.passwordMin') })
      return
    }
    setIsSaving(true)
    try {
      await authApi.changePassword(passwords.currentPassword, passwords.newPassword)
      setPasswords({ currentPassword: '', newPassword: '', confirmPassword: '' })
      toast({ title: t('settings.passwordChanged') })
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('settings.passwordFailed')
      toast({ variant: 'destructive', title: message })
    } finally {
      setIsSaving(false)
    }
  }

  const handleExportData = async () => {
    setIsSaving(true)
    try {
      const blob = await exportsApi.exportExcel({
        start_date: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        end_date: new Date().toISOString().split('T')[0],
        include_sales: true,
        include_advertising: true,
      })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'inthezon_full_export.xlsx'
      a.click()
      window.URL.revokeObjectURL(url)
      toast({ title: t('settings.exportDownloaded') })
    } catch {
      toast({ variant: 'destructive', title: t('settings.exportFailed') })
    } finally {
      setIsSaving(false)
    }
  }

  const handleDeleteAccount = async () => {
    if (!window.confirm(t('settings.deleteConfirm'))) {
      return
    }
    setIsSaving(true)
    try {
      await authApi.deleteAccount()
      useAuthStore.getState().logout()
    } catch {
      toast({ variant: 'destructive', title: t('settings.deleteFailed') })
      setIsSaving(false)
    }
  }

  const deleteApiKeysMutation = useMutation({
    mutationFn: () => authApi.deleteApiKeys(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      toast({ title: t('settings.apiKeysRemoved') })
    },
    onError: () => {
      toast({ variant: 'destructive', title: t('settings.apiKeysRemoveFailed') })
    },
  })

  const handleDeleteApiKeys = () => {
    if (!window.confirm(t('settings.apiKeysRemoveConfirm'))) return
    deleteApiKeysMutation.mutate()
  }

  const handleSaveApiKeys = (e: React.FormEvent) => {
    e.preventDefault()
    apiKeysMutation.mutate(apiKeys)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('settings.title')}</h1>
        <p className="text-muted-foreground">
          {t('settings.subtitle')}
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(value) => setSearchParams(value === 'profile' ? {} : { tab: value }, { replace: true })}
        className="space-y-4"
      >
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="accounts" className="gap-2">
            <Store className="h-4 w-4" /> {t('settings.tabAccounts')}
          </TabsTrigger>
          <TabsTrigger value="profile" className="gap-2">
            <User className="h-4 w-4" /> {t('settings.tabProfile')}
          </TabsTrigger>
          <TabsTrigger value="amazon-api" className="gap-2">
            <Key className="h-4 w-4" /> {t('settings.tabAmazonApi')}
          </TabsTrigger>
          <TabsTrigger value="notifications" className="gap-2">
            <Bell className="h-4 w-4" /> {t('settings.tabNotifications')}
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-2">
            <Shield className="h-4 w-4" /> {t('settings.tabSecurity')}
          </TabsTrigger>
          <TabsTrigger value="data" className="gap-2">
            <Database className="h-4 w-4" /> {t('settings.tabData')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="accounts" className="space-y-4">
          <AccountsSection embedded />
        </TabsContent>

        <TabsContent value="profile" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('settings.profileTitle')}</CardTitle>
              <CardDescription>
                {t('settings.profileDesc')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="fullName">{t('settings.fullName')}</Label>
                <Input
                  id="fullName"
                  value={profile.fullName}
                  onChange={(e) =>
                    setProfile({ ...profile, fullName: e.target.value })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">{t('common.email')}</Label>
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
                <Label>{t('settings.organization')}</Label>
                <Input value={organization?.name || ''} disabled />
                <p className="text-xs text-muted-foreground">
                  {t('settings.orgHelp')}
                </p>
              </div>
              <Button onClick={handleSaveProfile} disabled={isSaving}>
                {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('settings.saveChanges')}
              </Button>
            </CardContent>
          </Card>

          {/* Language */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Globe className="h-5 w-5" />
                {t('settings.language')}
              </CardTitle>
              <CardDescription>{t('settings.languageDesc')}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <Label>{t('settings.languageLabel')}</Label>
                <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
                  <SelectTrigger className="w-[200px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="it">Italiano</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="amazon-api">
          <Card>
            <CardHeader>
              <CardTitle>{t('settings.apiTitle')}</CardTitle>
              <CardDescription>
                {t('settings.apiDesc')}{' '}
                <a
                  href="https://sellercentral.amazon.com/apps/authorize/consent"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline text-primary"
                >
                  {t('settings.apiDescLink')}
                </a>.
              </CardDescription>
            </CardHeader>
            <form onSubmit={handleSaveApiKeys}>
              <CardContent className="space-y-5">
                {/* Current status */}
                {(() => {
                  if (!savedApiKeys) return null
                  const fields = [
                    { label: t('settings.clientId'), set: !!savedApiKeys.sp_api_client_id, value: savedApiKeys.sp_api_client_id },
                    { label: t('settings.clientSecret'), set: savedApiKeys.has_client_secret },
                    { label: t('settings.awsAccessKey'), set: !!savedApiKeys.sp_api_aws_access_key, value: savedApiKeys.sp_api_aws_access_key },
                    { label: t('settings.awsSecretKey'), set: savedApiKeys.has_aws_secret_key },
                    { label: t('settings.roleArn'), set: !!savedApiKeys.sp_api_role_arn, value: savedApiKeys.sp_api_role_arn },
                  ]
                  const setCount = fields.filter(f => f.set).length
                  const allSet = setCount === fields.length
                  const noneSet = setCount === 0

                  if (noneSet) {
                    return (
                      <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
                        <AlertTriangle className="h-4 w-4 shrink-0" />
                        {t('settings.noApiKeys')}
                      </div>
                    )
                  }

                  return (
                    <div className="rounded-md border bg-muted/30 p-4 space-y-2">
                      <p className="text-sm font-medium flex items-center gap-2">
                        {allSet ? (
                          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-amber-500" />
                        )}
                        {allSet ? t('settings.allApiKeysSet') : t('settings.partialApiKeys')}
                      </p>
                      <div className="grid gap-1 text-xs text-muted-foreground">
                        {fields.map((f) => (
                          <p key={f.label} className="flex items-center gap-1.5">
                            <span className={f.set ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>
                              {f.set ? t('settings.keySet') : t('settings.keyMissing')}
                            </span>
                            <span>{f.label}</span>
                            {f.value && <span className="font-mono ml-1">{f.value}</span>}
                          </p>
                        ))}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {t('settings.apiKeepCurrent')}
                      </p>
                    </div>
                  )
                })()}

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="clientId">{t('settings.clientId')}</Label>
                    <Input
                      id="clientId"
                      value={apiKeys.sp_api_client_id}
                      onChange={(e) => setApiKeys({ ...apiKeys, sp_api_client_id: e.target.value })}
                      placeholder={savedApiKeys?.sp_api_client_id || 'amzn1.application-oa2-client.xxx'}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="clientSecret">{t('settings.clientSecret')}</Label>
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
                    <Label htmlFor="awsAccessKey">{t('settings.awsAccessKey')}</Label>
                    <Input
                      id="awsAccessKey"
                      value={apiKeys.sp_api_aws_access_key}
                      onChange={(e) => setApiKeys({ ...apiKeys, sp_api_aws_access_key: e.target.value })}
                      placeholder={savedApiKeys?.sp_api_aws_access_key || 'AKIA...'}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="awsSecretKey">{t('settings.awsSecretKey')}</Label>
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
                  <Label htmlFor="roleArn">{t('settings.roleArn')}</Label>
                  <Input
                    id="roleArn"
                    value={apiKeys.sp_api_role_arn}
                    onChange={(e) => setApiKeys({ ...apiKeys, sp_api_role_arn: e.target.value })}
                    placeholder={savedApiKeys?.sp_api_role_arn || 'arn:aws:iam::123456789:role/sp-api'}
                  />
                  <p className="text-xs text-muted-foreground">
                    {t('settings.roleArnHelp')}
                  </p>
                </div>

                <div className="flex gap-3">
                  <Button type="submit" disabled={apiKeysMutation.isPending}>
                    {apiKeysMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {t('settings.saveApiKeys')}
                  </Button>
                  {savedApiKeys && (savedApiKeys.sp_api_client_id || savedApiKeys.has_client_secret) && (
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={handleDeleteApiKeys}
                      disabled={deleteApiKeysMutation.isPending}
                    >
                      {deleteApiKeysMutation.isPending
                        ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        : <Trash2 className="mr-2 h-4 w-4" />}
                      {t('settings.removeApiKeys')}
                    </Button>
                  )}
                </div>
              </CardContent>
            </form>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <CardTitle>{t('settings.notifTitle')}</CardTitle>
              <CardDescription>
                {t('settings.notifDesc')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{t('settings.dailyDigest')}</p>
                  <p className="text-sm text-muted-foreground">
                    {t('settings.dailyDigestDesc')}
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
                  <p className="font-medium">{t('settings.alertEmails')}</p>
                  <p className="text-sm text-muted-foreground">
                    {t('settings.alertEmailsDesc')}
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
                  <p className="font-medium">{t('settings.syncNotifications')}</p>
                  <p className="text-sm text-muted-foreground">
                    {t('settings.syncNotificationsDesc')}
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
                {t('settings.savePreferences')}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle>{t('settings.securityTitle')}</CardTitle>
              <CardDescription>
                {t('settings.securityDesc')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="currentPassword">{t('settings.currentPassword')}</Label>
                <Input
                  id="currentPassword"
                  type="password"
                  value={passwords.currentPassword}
                  onChange={(e) => setPasswords({ ...passwords, currentPassword: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="newPassword">{t('settings.newPassword')}</Label>
                <Input
                  id="newPassword"
                  type="password"
                  value={passwords.newPassword}
                  onChange={(e) => setPasswords({ ...passwords, newPassword: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirmPassword">{t('settings.confirmNewPassword')}</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  value={passwords.confirmPassword}
                  onChange={(e) => setPasswords({ ...passwords, confirmPassword: e.target.value })}
                />
              </div>
              <Button onClick={handleChangePassword} disabled={isSaving}>
                {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('settings.changePassword')}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="data">
          <Card>
            <CardHeader>
              <CardTitle>{t('settings.dataTitle')}</CardTitle>
              <CardDescription>
                {t('settings.dataDesc')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <h3 className="font-medium">{t('settings.dataRetention')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('settings.dataRetentionDesc')}
                </p>
              </div>
              <div className="space-y-2">
                <h3 className="font-medium">{t('settings.exportAll')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('settings.exportAllDesc')}
                </p>
                <Button variant="outline" onClick={handleExportData} disabled={isSaving}>
                  {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('settings.requestExport')}
                </Button>
              </div>
              <div className="space-y-2 pt-4 border-t">
                <h3 className="font-medium text-destructive">{t('settings.dangerZone')}</h3>
                <p className="text-sm text-muted-foreground">
                  {t('settings.dangerZoneDesc')}
                </p>
                <Button variant="destructive" onClick={handleDeleteAccount} disabled={isSaving}>
                  {t('settings.deleteAccount')}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
