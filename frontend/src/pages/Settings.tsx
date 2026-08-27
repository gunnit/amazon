import { useEffect, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, Loader2, Trash2 } from 'lucide-react'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useToast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/store/authStore'
import { authApi, exportsApi } from '@/services/api'
import type { MemberInvite, OfferedRole, OrgRole } from '@/services/api'
import { useTranslation } from '@/i18n'
import { apiErrorDetail } from '@/lib/apiError'
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
  const isAdmin = organization?.my_role === 'admin'

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
      const message = apiErrorDetail(error, t) || t('settings.profileFailed')
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
      const message = apiErrorDetail(error, t) || t('settings.orgUpdateFailed')
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
      const message = apiErrorDetail(error, t) || t('settings.passwordFailed')
      toast({ variant: 'destructive', title: message })
    } finally {
      setIsSaving(false)
    }
  }

  const handleExportData = async () => {
    setIsSaving(true)
    try {
      const blob = await exportsApi.exportExcelBundle({
        report_types: ['sales', 'advertising'],
        start_date: new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        end_date: new Date().toISOString().split('T')[0],
        language,
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
          <Button asChild variant="outline" size="sm" className={cn(ghostButton, 'mt-4')}>
            <Link to="/docs">{t('nav.docs')}</Link>
          </Button>
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
          {isAdmin && (
            <TabsTrigger value="users" className={tabTrigger}>
              {t('settings.tabUsers')}
            </TabsTrigger>
          )}
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
                  {savedApiKeys?.client_secret_age_days != null && (
                    <p
                      className={cn(
                        'mt-1.5 text-xs',
                        // ponytail: the measured age starts at "saved here", which is later
                        // than Amazon's issue date — so warn well before the 180-day deadline.
                        savedApiKeys.client_secret_age_days >= 120
                          ? 'text-amber-700 dark:text-amber-400'
                          : 'text-muted-foreground',
                      )}
                    >
                      {t('settings.secretAge', { days: savedApiKeys.client_secret_age_days })}{' '}
                      {t('settings.secretAgeHint')}
                      {savedApiKeys.client_secret_age_days >= 120 && ` ${t('settings.secretAgeWarning')}`}
                    </p>
                  )}
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
        {isAdmin && (
          <TabsContent value="users" className="mt-8">
            <UsersSection currentUserId={user?.id} />
          </TabsContent>
        )}
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

function UsersSection({ currentUserId }: { currentUserId?: string }) {
  const { t } = useTranslation()
  const { toast } = useToast()
  const queryClient = useQueryClient()
  const [invite, setInvite] = useState<MemberInvite | null>(null)
  const [copied, setCopied] = useState(false)
  const [form, setForm] = useState<{ email: string; full_name: string; role: OfferedRole }>({
    email: '',
    full_name: '',
    role: 'member',
  })

  const { data: members, isLoading } = useQuery({
    queryKey: ['org-members'],
    queryFn: () => authApi.getMembers(),
  })

  const showInvite = (result: MemberInvite) => {
    setInvite(result)
    setCopied(false)
    queryClient.invalidateQueries({ queryKey: ['org-members'] })
  }

  const createMutation = useMutation({
    mutationFn: () =>
      authApi.createMember({
        email: form.email,
        full_name: form.full_name || undefined,
        role: form.role,
      }),
    onSuccess: (result) => {
      showInvite(result)
      setForm({ email: '', full_name: '', role: 'member' })
      toast({ title: t('settings.usersCreated') })
    },
    onError: (error: unknown) => {
      toast({
        variant: 'destructive',
        title: apiErrorDetail(error, t) || t('settings.usersCreateFailed'),
      })
    },
  })

  const linkMutation = useMutation({
    mutationFn: (userId: string) => authApi.createMemberResetLink(userId),
    onSuccess: showInvite,
    onError: () => {
      toast({ variant: 'destructive', title: t('settings.usersLinkFailed') })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: { role?: OrgRole; is_active?: boolean } }) =>
      authApi.updateMember(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-members'] })
      toast({ title: t('settings.usersUpdated') })
    },
    onError: (error: unknown) => {
      toast({
        variant: 'destructive',
        title: apiErrorDetail(error, t) || t('settings.usersUpdateFailed'),
      })
    },
  })

  const copyLink = async () => {
    if (!invite) return
    try {
      await navigator.clipboard.writeText(invite.invite_link)
      setCopied(true)
      toast({ title: t('settings.usersCopied') })
    } catch {
      toast({ variant: 'destructive', title: t('settings.usersCopyFailed') })
    }
  }

  const roleLabel = (role: OrgRole) =>
    t(role === 'admin' ? 'settings.usersRoleAdmin' : role === 'member' ? 'settings.usersRoleMember' : 'settings.usersRoleViewer')

  return (
    <div className="space-y-10">
      <SettingsSection wide title={t('settings.usersTitle')} hint={t('settings.usersDesc')}>
        {invite && (
          <div className="rounded-sm border border-foreground/15 p-4">
            <p className={eyebrow}>{t('settings.usersInviteTitle')}</p>
            <p className="mt-1.5 text-sm font-medium">{invite.user.email}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-sm bg-foreground/[0.05] px-2 py-1.5 font-mono text-[11px]">
                {invite.invite_link}
              </code>
              <Button variant="outline" size="sm" className={ghostButton} onClick={copyLink}>
                {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
                {t('settings.usersCopy')}
              </Button>
            </div>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              {t('settings.usersInviteDesc', { days: invite.expires_in_days })}
            </p>
          </div>
        )}

        {isLoading ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        ) : !members?.length ? (
          <p className="text-sm text-muted-foreground">{t('settings.usersEmpty')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('settings.fullName')}</TableHead>
                <TableHead>{t('common.email')}</TableHead>
                <TableHead>{t('settings.usersRole')}</TableHead>
                <TableHead>{t('settings.usersStatus')}</TableHead>
                <TableHead className="text-right">{t('accounts.actions')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => {
                const isSelf = member.user_id === currentUserId
                return (
                  <TableRow key={member.user_id}>
                    <TableCell className="font-medium">{member.user.full_name || '—'}</TableCell>
                    <TableCell>{member.user.email}</TableCell>
                    <TableCell>
                      {isSelf ? (
                        roleLabel(member.role)
                      ) : (
                        <Select
                          value={member.role}
                          onValueChange={(role) =>
                            updateMutation.mutate({ userId: member.user_id, data: { role: role as OrgRole } })
                          }
                        >
                          <SelectTrigger className={cn(fieldInput, 'w-[160px]')}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="admin">{t('settings.usersRoleAdmin')}</SelectItem>
                            <SelectItem value="member">{t('settings.usersRoleMember')}</SelectItem>
                            {member.role === 'viewer' && (
                              <SelectItem value="viewer">{t('settings.usersRoleViewer')}</SelectItem>
                            )}
                          </SelectContent>
                        </Select>
                      )}
                    </TableCell>
                    <TableCell>
                      {member.user.is_active ? t('settings.usersActive') : t('settings.usersInactive')}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap justify-end gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className={ghostButton}
                          onClick={() => linkMutation.mutate(member.user_id)}
                          disabled={linkMutation.isPending}
                        >
                          {t('settings.usersNewLink')}
                        </Button>
                        {isSelf ? (
                          <span className="self-center text-xs text-muted-foreground">
                            {t('settings.usersSelfHint')}
                          </span>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            className={ghostButton}
                            onClick={() =>
                              updateMutation.mutate({
                                userId: member.user_id,
                                data: { is_active: !member.user.is_active },
                              })
                            }
                            disabled={updateMutation.isPending}
                          >
                            {member.user.is_active
                              ? t('settings.usersDeactivate')
                              : t('settings.usersActivate')}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </SettingsSection>

      <SettingsSection title={t('settings.usersAddTitle')} hint={t('settings.usersAddDesc')}>
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate()
          }}
        >
          <div>
            <Label htmlFor="memberEmail" className={eyebrow}>
              {t('common.email')}
            </Label>
            <Input
              id="memberEmail"
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder={t('login.emailPlaceholder')}
              className={cn(fieldInput, 'mt-1')}
            />
          </div>
          <div>
            <Label htmlFor="memberName" className={eyebrow}>
              {t('settings.fullName')}
            </Label>
            <Input
              id="memberName"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className={cn(fieldInput, 'mt-1')}
            />
          </div>
          <div>
            <Label className={eyebrow}>{t('settings.usersRole')}</Label>
            <Select value={form.role} onValueChange={(role) => setForm({ ...form, role: role as OfferedRole })}>
              <SelectTrigger className={cn(fieldInput, 'mt-1 w-[200px]')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">{t('settings.usersRoleAdmin')}</SelectItem>
                <SelectItem value="member">{t('settings.usersRoleMember')}</SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              {t('settings.usersRoleAdminDesc')}
              <br />
              {t('settings.usersRoleMemberDesc')}
            </p>
          </div>
          <Button type="submit" disabled={createMutation.isPending} className={inkButton}>
            {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('settings.usersAddSubmit')}
          </Button>
        </form>
      </SettingsSection>
    </div>
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
