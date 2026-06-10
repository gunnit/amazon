import { useState } from 'react'
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  LineChart,
  TrendingUp,
  Megaphone,
  Globe,
  Presentation,
  Newspaper,
  Target,
  Bell,
  Package,
  Settings,
  LogOut,
  Menu,
  X,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useAuthStore } from '@/store/authStore'
import { cn } from '@/lib/utils'
import { ChartGradients } from '@/lib/chart-theme'
import { ThemeToggle } from '@/components/ThemeToggle'
import { NotificationBell } from '@/components/NotificationBell'
import { useTranslation } from '@/i18n'

interface NavItemDef {
  key: string
  href: string
  icon: LucideIcon
}

const navGroups: { key: string; items: NavItemDef[] }[] = [
  {
    key: 'nav.group.analytics',
    items: [
      { key: 'nav.dashboard', href: '/', icon: LayoutDashboard },
      { key: 'nav.performance', href: '/performance', icon: LineChart },
      { key: 'nav.advertising', href: '/advertising', icon: Megaphone },
      { key: 'nav.forecasts', href: '/forecasts', icon: TrendingUp },
    ],
  },
  {
    key: 'nav.group.intelligence',
    items: [
      { key: 'nav.marketResearch', href: '/market-research', icon: Globe },
      { key: 'nav.brandAnalysis', href: '/brand-analysis', icon: Presentation },
      { key: 'nav.brandIntelligence', href: '/brand-intelligence', icon: Newspaper },
      { key: 'nav.recommendations', href: '/recommendations', icon: Target },
    ],
  },
  {
    key: 'nav.group.operations',
    items: [
      { key: 'nav.catalog', href: '/catalog', icon: Package },
      { key: 'nav.alerts', href: '/alerts', icon: Bell },
      { key: 'nav.settings', href: '/settings', icon: Settings },
    ],
  },
]

// Brand wordmark — theme-aware (the old version hardcoded text-white and
// disappeared on the light theme).
function Wordmark({ collapsed }: { collapsed?: boolean }) {
  return (
    <span className="text-xl font-bold text-foreground">{collapsed ? 'I' : 'Inthezon'}</span>
  )
}

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { user, organization, logout } = useAuthStore()
  const { t } = useTranslation()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-background">
      <ChartGradients />
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
          <Wordmark />
          <Button variant="ghost" size="icon" onClick={() => setSidebarOpen(false)}>
            <X className="h-6 w-6" />
          </Button>
        </div>
        <nav className="overflow-y-auto px-3 py-4">
          {navGroups.map((group, groupIndex) => (
            <div key={group.key} className={cn(groupIndex > 0 && 'mt-6')}>
              <p className="px-3 pb-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground/70">
                {t(group.key)}
              </p>
              <div className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const isActive = location.pathname === item.href
                  return (
                    <Link
                      key={item.key}
                      to={item.href}
                      onClick={() => setSidebarOpen(false)}
                      aria-current={isActive ? 'page' : undefined}
                      className={cn(
                        'flex items-center gap-2.5 border-l-2 px-3 py-2 text-[13px] font-medium transition-colors',
                        isActive
                          ? 'border-foreground bg-muted/70 text-foreground'
                          : 'border-transparent text-muted-foreground hover:bg-muted/40 hover:text-foreground',
                      )}
                    >
                      <item.icon className="h-4 w-4 shrink-0" />
                      {t(item.key)}
                    </Link>
                  )
                })}
              </div>
            </div>
          ))}
        </nav>
      </div>

      {/* Desktop sidebar */}
      <div
        className={cn(
          "hidden lg:fixed lg:inset-y-0 lg:flex lg:flex-col transition-[width] duration-300",
          sidebarCollapsed ? "lg:w-16" : "lg:w-64"
        )}
      >
        <div className="flex flex-col flex-grow bg-card border-r">
          <div
            className={cn(
              "relative flex h-16 items-center border-b",
              sidebarCollapsed ? "justify-center px-2" : "justify-between px-5"
            )}
          >
            {!sidebarCollapsed ? <Wordmark /> : null}
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground"
              onClick={() => setSidebarCollapsed((prev) => !prev)}
              aria-label={sidebarCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
            >
              {sidebarCollapsed ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronLeft className="h-4 w-4" />
              )}
            </Button>
          </div>
          <nav className={cn('flex-1 overflow-y-auto py-4', sidebarCollapsed ? 'px-2' : 'px-3')}>
            {navGroups.map((group, groupIndex) => (
              <div key={group.key} className={cn(groupIndex > 0 && 'mt-6')}>
                {!sidebarCollapsed ? (
                  <p className="px-3 pb-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground/70">
                    {t(group.key)}
                  </p>
                ) : groupIndex > 0 ? (
                  <div aria-hidden="true" className="mx-2 mb-4 border-t border-border" />
                ) : null}
                <div className="flex flex-col gap-0.5">
                  {group.items.map((item) => {
                    const isActive = location.pathname === item.href
                    return (
                      <Link
                        key={item.key}
                        to={item.href}
                        title={sidebarCollapsed ? t(item.key) : undefined}
                        aria-current={isActive ? 'page' : undefined}
                        className={cn(
                          'flex items-center gap-2.5 text-[13px] font-medium transition-colors',
                          sidebarCollapsed
                            ? 'justify-center rounded-sm px-2 py-2'
                            : 'border-l-2 px-3 py-2',
                          isActive
                            ? sidebarCollapsed
                              ? 'bg-muted text-foreground'
                              : 'border-foreground bg-muted/70 text-foreground'
                            : sidebarCollapsed
                              ? 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'
                              : 'border-transparent text-muted-foreground hover:bg-muted/40 hover:text-foreground',
                        )}
                      >
                        <item.icon className="h-4 w-4 shrink-0" />
                        {sidebarCollapsed ? (
                          <span className="sr-only">{t(item.key)}</span>
                        ) : (
                          <span className="truncate">{t(item.key)}</span>
                        )}
                      </Link>
                    )
                  })}
                </div>
              </div>
            ))}
          </nav>
          <div className={cn('border-t', sidebarCollapsed ? 'p-2' : 'p-3')}>
            <div
              className={cn(
                'flex items-center gap-3 px-2 py-1.5',
                sidebarCollapsed && 'justify-center px-0'
              )}
            >
              {!sidebarCollapsed && (
                <div className="flex-1 min-w-0">
                  <p className="truncate text-xs font-medium text-foreground">
                    {user?.full_name || user?.email}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                    {organization?.name}
                  </p>
                </div>
              )}
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground"
                onClick={handleLogout}
                aria-label={t('nav.logout')}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div
        className={cn(
          "lg:pl-64 transition-[padding] duration-300",
          sidebarCollapsed && "lg:pl-16"
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
            <NotificationBell />
            <ThemeToggle />
            <Popover>
              <PopoverTrigger asChild>
                <button className="hidden sm:flex items-center gap-2 text-sm rounded-md px-3 py-1.5 hover:bg-muted transition-colors">
                  <span className="text-muted-foreground">{t('nav.organization')}</span>
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
                  {t('nav.orgSettings')}
                </Link>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm hover:bg-muted transition-colors w-full text-left"
                >
                  <LogOut className="h-4 w-4 text-muted-foreground" />
                  {t('nav.logout')}
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
