import { useEffect, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
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
import { GoogleSheetsIntegration } from '@/components/settings/GoogleSheetsIntegration'
import { cn } from '@/lib/utils'
import { eyebrow, fieldInput, ghostButton, inkButton, tabTrigger } from '@/lib/editorial'
import { SectionMark } from '@/components/shared/SectionMark'
import type { Language } from '@/store/languageStore'
import type { ApiKeysResponse } from '@/types'

// Destructive actions keep the destructive variant but pick up the page's
// mono-caps button voice.
const dangerButton = 'rounded-sm font-mono text-xs uppercase tracking-[0.14em]'

function maskArn(arn: string): string {
  // arn:aws:iam::905355900769:role/API -> arn:aws:iam::•••••••••769:role/API
  return arn.replace(/(arn:aws:iam::)(\d+)(:role\/.*)/, (_, prefix, account, suffix) => {
    const tail = account.slice(-3)
    return `${prefix}${'•'.repeat(Math.max(account.length - 3, 0))}${tail}${suffix}`
  })
}

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

  const [orgName, setOrgName] = useState(organization?.name || '')

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

  // Real outbound-email delivery state (SendGrid config + sender).
  const { data: emailStatus } = useQuery({
    queryKey: ['email-status'],
    queryFn: () => authApi.getEmailStatus(),
  })

  useEffect(() => {
    if (organization) {
      setOrgName(organization.name)
    }
  }, [organization])

  useEffect(() => {
    if (savedNotifications) {
      setNotifications({
        dailyDigest: savedNotifications.daily_digest,
        alertEmails: savedNotifications.alert_emails,
        syncNotifications: savedNotifications.sync_notifications,
      })
    }
  }, [savedNotifications])

  useEffect(() => {
    const googleStatus = searchParams.get('google')
    if (!googleStatus) return

    if (googleStatus === 'connected') {
      toast({ title: t('googleSheets.connectedSuccess') })
    } else if (googleStatus === 'error') {
      toast({ variant: 'destructive', title: t('googleSheets.connectFailed') })
    }

    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('google')
    setSearchParams(nextParams, { replace: true })
  }, [searchParams, setSearchParams, t, toast])

  // API Keys state
  const [apiKeys, setApiKeys] = useState({
    sp_api_client_id: '',
    sp_api_client_secret: '',
    sp_api_aws_access_key: '',
    sp_api_aws_secret_key: '',
    sp_api_role_arn: '',
    advertising_client_id: '',
    advertising_client_secret: '',
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
      if (data.advertising_client_id) payload.advertising_client_id = data.advertising_client_id
      if (data.advertising_client_secret) payload.advertising_client_secret = data.advertising_client_secret
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
        advertising_client_id: '',
        advertising_client_secret: '',
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

  const handleSaveOrganization = async () => {
    setIsSaving(true)
    try {
      const updated = await authApi.updateOrganization({ name: orgName })
      useAuthStore.getState().setOrganization(updated)
      toast({ title: t('settings.orgUpdated') })
    } catch (error: unknown) {
      const message =
        (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        t('settings.orgUpdateFailed')
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
    <div className="space-y-10 pb-4">
      {/* ─── Masthead ────────────────────────────────────────────────── */}
      <header className="ba-rise">
        <div aria-hidden="true" className="border-t-[3px] border-foreground" />
        <div aria-hidden="true" className="mt-[3px] border-t border-foreground/30" />
        <div className="pt-6">
          <h1 className="text-3xl font-bold tracking-tight">{t('settings.title')}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            {t('settings.subtitle')}
          </p>
        </div>
      </header>

      <Tabs
        value={activeTab}
        onValueChange={(value) => setSearchParams(value === 'profile' ? {} : { tab: value }, { replace: true })}
        className="ba-rise ba-rise-2"
      >
        <TabsList className="h-auto w-full flex-wrap justify-start gap-x-7 gap-y-1 rounded-none border-b border-foreground/15 bg-transparent p-0 text-muted-foreground">
          <TabsTrigger value="accounts" className={tabTrigger}>
            {t('settings.tabAccounts')}
          </TabsTrigger>
          <TabsTrigger value="profile" className={tabTrigger}>
            {t('settings.tabProfile')}
          </TabsTrigger>
          <TabsTrigger value="amazon-api" className={tabTrigger}>
            {t('settings.tabAmazonApi')}
          </TabsTrigger>
          <TabsTrigger value="notifications" className={tabTrigger}>
            {t('settings.tabNotifications')}
          </TabsTrigger>
          <TabsTrigger value="integrations" className={tabTrigger}>
            {t('settings.tabIntegrations')}
          </TabsTrigger>
          <TabsTrigger value="security" className={tabTrigger}>
            {t('settings.tabSecurity')}
          </TabsTrigger>
          <TabsTrigger value="data" className={tabTrigger}>
            {t('settings.tabData')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="accounts" className="mt-8">
          <SettingsSection title={t('accounts.title')} hint={t('settings.accountsMovedDesc')}>
            <Button asChild variant="outline" className={ghostButton}>
              <Link to="/accounts">{t('settings.openAccounts')}</Link>
            </Button>
          </SettingsSection>
        </TabsContent>

        <TabsContent value="profile" className="mt-8 space-y-10">
          <SettingsSection title={t('settings.profileTitle')} hint={t('settings.profileDesc')}>
            <div>
              <Label htmlFor="fullName" className={eyebrow}>
                {t('settings.fullName')}
              </Label>
              <Input
                id="fullName"
                value={profile.fullName}
                onChange={(e) => setProfile({ ...profile, fullName: e.target.value })}
                className={cn(fieldInput, 'mt-1')}
              />
            </div>
            <div>
              <Label htmlFor="email" className={eyebrow}>
                {t('common.email')}
              </Label>
              <Input
                id="email"
                type="email"
                value={profile.email}
                onChange={(e) => setProfile({ ...profile, email: e.target.value })}
                className={cn(fieldInput, 'mt-1')}
              />
            </div>
            <Button onClick={handleSaveProfile} disabled={isSaving} className={inkButton}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('settings.saveChanges')}
            </Button>
          </SettingsSection>

          {/* Organization */}
          <SettingsSection title={t('settings.organization')}>
            <div>
              <Label htmlFor="orgName" className={eyebrow}>
                {t('settings.organization')}
              </Label>
              <Input
                id="orgName"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className={cn(fieldInput, 'mt-1')}
              />
            </div>
            <Button onClick={handleSaveOrganization} disabled={isSaving} className={inkButton}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('settings.saveChanges')}
            </Button>
          </SettingsSection>

          {/* Language */}
          <SettingsSection title={t('settings.language')} hint={t('settings.languageDesc')}>
            <div>
              <Label className={eyebrow}>{t('settings.languageLabel')}</Label>
              <Select value={language} onValueChange={(v) => setLanguage(v as Language)}>
                <SelectTrigger className={cn(fieldInput, 'mt-1 w-[200px]')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="it">Italiano</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </SettingsSection>
        </TabsContent>

        <TabsContent value="amazon-api" className="mt-8">
          <form onSubmit={handleSaveApiKeys}>
            <SettingsSection
              wide
              title={t('settings.apiTitle')}
              hint={
                <>
                  {t('settings.apiDesc')}{' '}
                  <a
                    href="https://sellercentral.amazon.com/apps/authorize/consent"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline decoration-dotted underline-offset-4 text-foreground"
                  >
                    {t('settings.apiDescLink')}
                  </a>
                  .
                </>
              }
            >
              {/* Current status — credential manifest */}
              {(() => {
                if (!savedApiKeys) return null
                const fields = [
                  { label: t('settings.clientId'), set: !!savedApiKeys.sp_api_client_id, value: savedApiKeys.sp_api_client_id },
                  { label: t('settings.clientSecret'), set: savedApiKeys.has_client_secret },
                  { label: t('settings.awsAccessKey'), set: !!savedApiKeys.sp_api_aws_access_key, value: savedApiKeys.sp_api_aws_access_key },
                  { label: t('settings.awsSecretKey'), set: savedApiKeys.has_aws_secret_key },
                  { label: t('settings.roleArn'), set: !!savedApiKeys.sp_api_role_arn, value: savedApiKeys.sp_api_role_arn ? maskArn(savedApiKeys.sp_api_role_arn) : undefined },
                  { label: t('accounts.adsClientId'), set: !!savedApiKeys.advertising_client_id, value: savedApiKeys.advertising_client_id },
                  { label: t('accounts.adsClientSecret'), set: savedApiKeys.has_advertising_client_secret },
                ]
                const setCount = fields.filter(f => f.set).length
                const allSet = setCount === fields.length
                const noneSet = setCount === 0

                if (noneSet) {
                  return (
                    <div className="border-l-2 border-amber-500 py-1 pl-4 text-sm leading-6 text-amber-700 dark:text-amber-400">
                      {t('settings.noApiKeys')}
                    </div>
                  )
                }

                return (
                  <div className="rounded-sm border border-foreground/15 p-4">
                    <p
                      className={cn(
                        'font-mono text-[10px] font-semibold uppercase tracking-[0.18em]',
                        allSet
                          ? 'text-emerald-700 dark:text-emerald-400'
                          : 'text-amber-700 dark:text-amber-400',
                      )}
                    >
                      {allSet ? t('settings.allApiKeysSet') : t('settings.partialApiKeys')}
                    </p>
                    <div className="mt-2 divide-y divide-foreground/10">
                      {fields.map((f) => (
                        <div key={f.label} className="flex items-baseline gap-2.5 py-2">
                          <span className="shrink-0 text-xs font-medium">{f.label}</span>
                          {f.value ? (
                            <span className="truncate font-mono text-[11px] text-muted-foreground">
                              {f.value}
                            </span>
                          ) : null}
                          <span
                            aria-hidden="true"
                            className="flex-1 self-center border-b border-dotted border-foreground/30"
                          />
                          <span
                            aria-hidden="true"
                            className={cn(
                              'h-1.5 w-1.5 shrink-0 self-center rounded-full',
                              f.set ? 'bg-emerald-500' : 'bg-amber-500',
                            )}
                          />
                          <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                            {f.set ? t('settings.keySet') : t('settings.keyMissing')}
                          </span>
                        </div>
                      ))}
                    </div>
                    <p className="mt-3 text-xs leading-5 text-muted-foreground">
                      {t('settings.apiKeepCurrent')}
                    </p>
                  </div>
                )
              })()}

              <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
                <div>
                  <Label htmlFor="clientId" className={eyebrow}>
                    {t('settings.clientId')}
                  </Label>
                  <Input
                    id="clientId"
                    value={apiKeys.sp_api_client_id}
                    onChange={(e) => setApiKeys({ ...apiKeys, sp_api_client_id: e.target.value })}
                    placeholder={savedApiKeys?.sp_api_client_id || 'amzn1.application-oa2-client.xxx'}
                    className={cn(fieldInput, 'mt-1')}
                  />
                </div>
                <div>
                  <Label htmlFor="clientSecret" className={eyebrow}>
                    {t('settings.clientSecret')}
                  </Label>
                  <Input
                    id="clientSecret"
                    type="password"
                    value={apiKeys.sp_api_client_secret}
                    onChange={(e) => setApiKeys({ ...apiKeys, sp_api_client_secret: e.target.value })}
                    placeholder={savedApiKeys?.has_client_secret ? '••••••••' : 'Your client secret'}
                    className={cn(fieldInput, 'mt-1')}
                  />
                </div>
                <div>
                  <Label htmlFor="awsAccessKey" className={eyebrow}>
                    {t('settings.awsAccessKey')}
                  </Label>
                  <Input
                    id="awsAccessKey"
                    value={apiKeys.sp_api_aws_access_key}
                    onChange={(e) => setApiKeys({ ...apiKeys, sp_api_aws_access_key: e.target.value })}
                    placeholder={savedApiKeys?.sp_api_aws_access_key || 'AKIA...'}
                    className={cn(fieldInput, 'mt-1')}
                  />
                </div>
                <div>
                  <Label htmlFor="awsSecretKey" className={eyebrow}>
                    {t('settings.awsSecretKey')}
                  </Label>
                  <Input
                    id="awsSecretKey"
                    type="password"
                    value={apiKeys.sp_api_aws_secret_key}
                    onChange={(e) => setApiKeys({ ...apiKeys, sp_api_aws_secret_key: e.target.value })}
                    placeholder={savedApiKeys?.has_aws_secret_key ? '••••••••' : 'Your AWS secret key'}
                    className={cn(fieldInput, 'mt-1')}
                  />
                </div>
              </div>

              <div>
                <Label htmlFor="roleArn" className={eyebrow}>
                  {t('settings.roleArn')}
                </Label>
                <Input
                  id="roleArn"
                  value={apiKeys.sp_api_role_arn}
                  onChange={(e) => setApiKeys({ ...apiKeys, sp_api_role_arn: e.target.value })}
                  placeholder={savedApiKeys?.sp_api_role_arn ? maskArn(savedApiKeys.sp_api_role_arn) : 'arn:aws:iam::123456789:role/sp-api'}
                  className={cn(fieldInput, 'mt-1')}
                />
                <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                  {t('settings.roleArnHelp')}
                </p>
              </div>

              <div className="grid gap-x-8 gap-y-5 md:grid-cols-2">
                <div>
                  <Label htmlFor="advertisingClientId" className={eyebrow}>
                    {t('accounts.adsClientId')}
                  </Label>
                  <Input
                    id="advertisingClientId"
                    value={apiKeys.advertising_client_id}
                    onChange={(e) => setApiKeys({ ...apiKeys, advertising_client_id: e.target.value })}
                    placeholder={savedApiKeys?.advertising_client_id || 'amzn1.application-oa2-client.xxx'}
                    className={cn(fieldInput, 'mt-1')}
                  />
                </div>
                <div>
                  <Label htmlFor="advertisingClientSecret" className={eyebrow}>
                    {t('accounts.adsClientSecret')}
                  </Label>
                  <Input
                    id="advertisingClientSecret"
                    type="password"
                    value={apiKeys.advertising_client_secret}
                    onChange={(e) => setApiKeys({ ...apiKeys, advertising_client_secret: e.target.value })}
                    placeholder={savedApiKeys?.has_advertising_client_secret ? '••••••••' : 'Your Ads client secret'}
                    className={cn(fieldInput, 'mt-1')}
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-3 border-t border-foreground/10 pt-5">
                <Button type="submit" disabled={apiKeysMutation.isPending} className={inkButton}>
                  {apiKeysMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('settings.saveApiKeys')}
                </Button>
                {savedApiKeys && (
                  savedApiKeys.sp_api_client_id ||
                  savedApiKeys.has_client_secret ||
                  savedApiKeys.advertising_client_id ||
                  savedApiKeys.has_advertising_client_secret
                ) && (
                  <Button
                    type="button"
                    variant="destructive"
                    className={dangerButton}
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
            </SettingsSection>
          </form>
        </TabsContent>

        <TabsContent value="notifications" className="mt-8">
          <SettingsSection title={t('settings.notifTitle')} hint={t('settings.notifDesc')}>
            {emailStatus && (
              <div
                className={cn(
                  'border-l-2 py-1 pl-4',
                  emailStatus.status === 'configured' ? 'border-emerald-500' : 'border-amber-500',
                )}
              >
                <p
                  className={cn(
                    'text-sm font-medium',
                    emailStatus.status === 'configured'
                      ? 'text-emerald-700 dark:text-emerald-400'
                      : 'text-amber-700 dark:text-amber-400',
                  )}
                >
                  {emailStatus.status === 'configured'
                    ? t('settings.emailDeliveryConfigured')
                    : t('settings.emailDeliveryMissing')}
                </p>
                {emailStatus.detail && (
                  <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{emailStatus.detail}</p>
                )}
              </div>
            )}
            <div>
              <ToggleRow
                title={t('settings.dailyDigest')}
                desc={t('settings.dailyDigestDesc')}
                checked={notifications.dailyDigest}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, dailyDigest: checked })
                }
              />
              <ToggleRow
                title={t('settings.alertEmails')}
                desc={t('settings.alertEmailsDesc')}
                checked={notifications.alertEmails}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, alertEmails: checked })
                }
              />
              <ToggleRow
                title={t('settings.syncNotifications')}
                desc={t('settings.syncNotificationsDesc')}
                checked={notifications.syncNotifications}
                onCheckedChange={(checked) =>
                  setNotifications({ ...notifications, syncNotifications: checked })
                }
              />
            </div>
            <Button onClick={handleSaveNotifications} disabled={isSaving} className={inkButton}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('settings.savePreferences')}
            </Button>
          </SettingsSection>
        </TabsContent>

        <TabsContent value="integrations" className="mt-8 space-y-4">
          <GoogleSheetsIntegration />
        </TabsContent>

        <TabsContent value="security" className="mt-8">
          <SettingsSection title={t('settings.securityTitle')} hint={t('settings.securityDesc')}>
            <div>
              <Label htmlFor="currentPassword" className={eyebrow}>
                {t('settings.currentPassword')}
              </Label>
              <Input
                id="currentPassword"
                type="password"
                value={passwords.currentPassword}
                onChange={(e) => setPasswords({ ...passwords, currentPassword: e.target.value })}
                className={cn(fieldInput, 'mt-1')}
              />
            </div>
            <div>
              <Label htmlFor="newPassword" className={eyebrow}>
                {t('settings.newPassword')}
              </Label>
              <Input
                id="newPassword"
                type="password"
                value={passwords.newPassword}
                onChange={(e) => setPasswords({ ...passwords, newPassword: e.target.value })}
                className={cn(fieldInput, 'mt-1')}
              />
            </div>
            <div>
              <Label htmlFor="confirmPassword" className={eyebrow}>
                {t('settings.confirmNewPassword')}
              </Label>
              <Input
                id="confirmPassword"
                type="password"
                value={passwords.confirmPassword}
                onChange={(e) => setPasswords({ ...passwords, confirmPassword: e.target.value })}
                className={cn(fieldInput, 'mt-1')}
              />
            </div>
            <Button onClick={handleChangePassword} disabled={isSaving} className={inkButton}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('settings.changePassword')}
            </Button>
          </SettingsSection>
        </TabsContent>

        <TabsContent value="data" className="mt-8">
          <SettingsSection title={t('settings.dataTitle')} hint={t('settings.dataDesc')}>
            <div>
              <p className="text-sm font-medium">{t('settings.dataRetention')}</p>
              <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                {t('settings.dataRetentionDesc')}
              </p>
            </div>
            <div className="border-t border-foreground/10 pt-5">
              <p className="text-sm font-medium">{t('settings.exportAll')}</p>
              <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                {t('settings.exportAllDesc')}
              </p>
              <Button
                variant="outline"
                className={cn(ghostButton, 'mt-3')}
                onClick={handleExportData}
                disabled={isSaving}
              >
                {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('settings.requestExport')}
              </Button>
            </div>
            <div className="border-l-2 border-rose-500 pl-4 pt-1">
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-700 dark:text-rose-400">
                {t('settings.dangerZone')}
              </p>
              <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
                {t('settings.dangerZoneDesc')}
              </p>
              <Button
                variant="destructive"
                className={cn(dangerButton, 'mt-3')}
                onClick={handleDeleteAccount}
                disabled={isSaving}
              >
                {t('settings.deleteAccount')}
              </Button>
            </div>
          </SettingsSection>
        </TabsContent>
      </Tabs>
    </div>
  )
}

/* ─── small inline pieces ────────────────────────────────────────── */

function SettingsSection({
  title,
  hint,
  wide,
  children,
}: {
  title: string
  hint?: ReactNode
  wide?: boolean
  children: ReactNode
}) {
  return (
    <section>
      <SectionMark title={title} hint={hint} />
      <div className={cn('mt-6 space-y-5', wide ? 'max-w-3xl' : 'max-w-2xl')}>{children}</div>
    </section>
  )
}

function ToggleRow({
  title,
  desc,
  checked,
  onCheckedChange,
}: {
  title: string
  desc: string
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-6 border-b border-foreground/10 py-3.5">
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{desc}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={title} />
    </div>
  )
}
