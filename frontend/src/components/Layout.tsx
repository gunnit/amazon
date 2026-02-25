import { useState } from 'react'
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Store,
  FileText,
  BarChart3,
  TrendingUp,
  Settings,
  LogOut,
  Menu,
  X,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useAuthStore } from '@/store/authStore'
import { cn } from '@/lib/utils'
import { ThemeToggle } from '@/components/ThemeToggle'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Accounts', href: '/accounts', icon: Store },
  { name: 'Reports', href: '/reports', icon: FileText },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'Forecasts', href: '/forecasts', icon: TrendingUp },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { user, organization, logout } = useAuthStore()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-background">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-gray-900/80 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Mobile sidebar */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 w-72 bg-card transform transition-transform duration-300 ease-in-out lg:hidden",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex items-center justify-between h-16 px-6 border-b">
          <span className="text-xl font-bold text-primary">Inthezon</span>
          <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(false)}>
            <X className="h-6 w-6" />
          </Button>
        </div>
        <nav className="flex flex-col gap-1 p-4">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href
            return (
              <Link
                key={item.name}
                to={item.href}
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-muted"
                )}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </Link>
            )
          })}
        </nav>
      </div>

      {/* Desktop sidebar */}
      <div
        className={cn(
          "hidden lg:fixed lg:inset-y-0 lg:flex lg:flex-col transition-[width] duration-300",
          sidebarCollapsed ? "lg:w-20" : "lg:w-72"
        )}
      >
        <div className="flex flex-col flex-grow bg-card border-r">
          <div
            className={cn(
              "relative flex items-center h-16 border-b",
              sidebarCollapsed ? "px-3 justify-center" : "px-6 justify-between"
            )}
          >
            <span className="text-xl font-bold text-primary">
              {sidebarCollapsed ? "I" : "Inthezon"}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className={cn(sidebarCollapsed && "absolute right-2")}
              onClick={() => setSidebarCollapsed((prev) => !prev)}
              aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {sidebarCollapsed ? (
                <ChevronRight className="h-5 w-5" />
              ) : (
                <ChevronLeft className="h-5 w-5" />
              )}
            </Button>
          </div>
          <nav className="flex flex-col gap-1 p-4 flex-1">
            {navigation.map((item) => {
              const isActive = location.pathname === item.href
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted",
                    sidebarCollapsed && "justify-center"
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  {sidebarCollapsed ? (
                    <span className="sr-only">{item.name}</span>
                  ) : (
                    item.name
                  )}
                </Link>
              )
            })}
          </nav>
          <div className="p-4 border-t">
            <div
              className={cn(
                "flex items-center gap-3 px-3 py-2",
                sidebarCollapsed && "justify-center"
              )}
            >
              {!sidebarCollapsed && (
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {user?.full_name || user?.email}
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {organization?.name}
                  </p>
                </div>
              )}
              <Button variant="ghost" size="icon" onClick={handleLogout}>
                <LogOut className="h-5 w-5" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div
        className={cn(
          "lg:pl-72 transition-[padding] duration-300",
          sidebarCollapsed && "lg:pl-20"
        )}
      >
        {/* Top bar */}
        <header className="sticky top-0 z-30 flex items-center h-16 px-4 bg-card border-b lg:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-6 w-6" />
          </Button>
          <div className="flex-1" />
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <Popover>
              <PopoverTrigger asChild>
                <button className="hidden sm:flex items-center gap-2 text-sm rounded-md px-3 py-1.5 hover:bg-muted transition-colors">
                  <span className="text-muted-foreground">Organization:</span>
                  <span className="font-medium">{organization?.name}</span>
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-56 p-2">
                <div className="px-2 py-1.5 mb-1">
                  <p className="text-sm font-medium">{organization?.name}</p>
                  <p className="text-xs text-muted-foreground">{user?.email}</p>
                </div>
                <div className="h-px bg-border my-1" />
                <Link
                  to="/settings"
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm hover:bg-muted transition-colors w-full"
                >
                  <Settings className="h-4 w-4 text-muted-foreground" />
                  Organization settings
                </Link>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm hover:bg-muted transition-colors w-full text-left"
                >
                  <LogOut className="h-4 w-4 text-muted-foreground" />
                  Log out
                </button>
              </PopoverContent>
            </Popover>
          </div>
        </header>

        {/* Page content */}
        <main className="p-4 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
