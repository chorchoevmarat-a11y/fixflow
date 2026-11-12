'use client'

import React, { useEffect } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  LayoutDashboard,
  ClipboardList,
  Calendar,
  Building,
  Package,
  Wrench,
  BarChart3,
  Users,
  Settings,
  FolderTree,
  ShieldCheck,
  LogOut,
  Menu,
} from 'lucide-react'
import { useAuth } from '@/hooks/use-auth'
import { getToken } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { OrgSwitcher } from '@/components/org-switcher'
import { NotificationBell } from '@/components/notification-bell'
import { Separator } from '@/components/ui/separator'

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/requests', label: 'Service Requests', icon: ClipboardList },
  { href: '/schedule', label: 'Schedule', icon: Calendar },
  { href: '/properties', label: 'Properties', icon: Building },
  { href: '/inventory', label: 'Inventory', icon: Package },
  { href: '/maintenance', label: 'Maintenance Plans', icon: Wrench },
  { href: '/reports', label: 'Reports', icon: BarChart3 },
]

const adminItems = [
  { href: '/admin/organization', label: 'Organization', icon: Settings },
  { href: '/admin/staff', label: 'Staff & Roles', icon: Users },
  { href: '/admin/categories', label: 'Categories', icon: FolderTree },
  { href: '/admin/audit', label: 'Audit Log', icon: ShieldCheck },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()
  const { user, isLoading, logout } = useAuth()
  const [mobileMenuOpen, setMobileMenuOpen] = React.useState(false)

  useEffect(() => {
    const token = getToken()
    if (!token && !isLoading) {
      router.replace('/login')
    }
  }, [isLoading, router])

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  const renderNavLinks = () => (
    <div className="space-y-6">
      <div className="space-y-1">
        <p className="px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Operations
        </p>
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobileMenuOpen(false)}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          )
        })}
      </div>

      <div className="space-y-1">
        <p className="px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Administration
        </p>
        {adminItems.map((item) => {
          const Icon = item.icon
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobileMenuOpen(false)}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              }`}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          )
        })}
      </div>
    </div>
  )

  return (
    <div className="flex min-h-screen bg-muted/20">
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-64 flex-col border-r bg-background shrink-0">
        <div className="flex h-14 items-center border-b px-4 gap-2 font-bold text-lg text-primary">
          <Wrench className="w-5 h-5" />
          <span>FixFlow</span>
        </div>
        <div className="flex-1 overflow-y-auto p-4">{renderNavLinks()}</div>
        <div className="border-t p-4 flex items-center justify-between">
          <div className="flex flex-col min-w-0">
            <span className="text-sm font-medium truncate">{user?.full_name || 'User'}</span>
            <span className="text-xs text-muted-foreground capitalize">{user?.role || 'Staff'}</span>
          </div>
          <Button variant="ghost" size="icon" onClick={() => logout()} title="Sign out">
            <LogOut className="h-4 w-4 text-muted-foreground hover:text-destructive" />
          </Button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col min-w-0">
        <header className="sticky top-0 z-40 flex h-14 items-center justify-between border-b bg-background px-4 sm:px-6">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              <Menu className="h-5 w-5" />
            </Button>
            <OrgSwitcher />
          </div>

          <div className="flex items-center gap-2">
            <NotificationBell />
            <Separator orientation="vertical" className="h-6 mx-1" />
            <div className="text-xs text-muted-foreground hidden sm:block">
              {user?.email}
            </div>
          </div>
        </header>

        {/* Mobile menu drawer */}
        {mobileMenuOpen && (
          <div className="md:hidden fixed inset-0 z-50 bg-black/50" onClick={() => setMobileMenuOpen(false)}>
            <div
              className="w-64 h-full bg-background p-4 flex flex-col justify-between"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                <div className="flex items-center gap-2 font-bold text-lg text-primary mb-6">
                  <Wrench className="w-5 h-5" />
                  <span>FixFlow</span>
                </div>
                {renderNavLinks()}
              </div>
              <div className="border-t pt-4 flex items-center justify-between">
                <span className="text-sm font-medium">{user?.full_name}</span>
                <Button variant="ghost" size="icon" onClick={() => logout()}>
                  <LogOut className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        )}

        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
