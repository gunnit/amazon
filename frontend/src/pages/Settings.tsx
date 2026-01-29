import { useState } from 'react'
import { User, Bell, Shield, Database, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/store/authStore'

export default function Settings() {
  const { user, organization } = useAuthStore()
  const { toast } = useToast()
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

  const handleSaveProfile = async () => {
    setIsSaving(true)
    try {
      // API call would go here
      await new Promise((resolve) => setTimeout(resolve, 1000))
      toast({ title: 'Profile updated successfully' })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Failed to update profile',
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
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Failed to save settings',
      })
    } finally {
      setIsSaving(false)
    }
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
