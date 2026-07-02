import { useIsMutating, useQuery } from '@tanstack/react-query'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowLeftRight,
  Building2,
  CreditCard,
  FileText,
  HardHat,
  House,
  IndianRupee,
  Landmark,
  LayoutDashboard,
  Mail,
  NotebookPen,
  PieChart,
  Repeat,
  Scale,
  Settings,
  Shield,
  Target,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { IndeterminateProgressBar } from '@/components/ui/IndeterminateProgressBar'
import { fetchEmailInboxStats } from '@/lib/api'

const NAV: Array<{ to: string; label: string; icon: LucideIcon }> = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/accounts', label: 'Accounts', icon: Wallet },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/budget', label: 'Budget', icon: PieChart },
  { to: '/debt', label: 'Debt', icon: Landmark },
  { to: '/credit-cards', label: 'Credit cards', icon: CreditCard },
  { to: '/recurring', label: 'Subscriptions & EMIs', icon: Repeat },
  { to: '/investments', label: 'Investments', icon: TrendingUp },
  { to: '/net-worth', label: 'Net worth', icon: Scale },
  { to: '/assets', label: 'Assets', icon: Building2 },
  { to: '/construction', label: 'Construction', icon: HardHat },
  { to: '/home', label: 'Home Inventory', icon: House },
  { to: '/insurance', label: 'Insurance', icon: Shield },
  { to: '/goals', label: 'Goals', icon: Target },
  { to: '/income', label: 'Income & tax', icon: IndianRupee },
  { to: '/reports', label: 'Reports', icon: FileText },
  { to: '/journal', label: 'Journal', icon: NotebookPen },
  { to: '/email-inbox', label: 'Gmail Inbox', icon: Mail },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function AppShell() {
  const fileUploadBusy = useIsMutating({ mutationKey: ['file-upload'] }) > 0

  const inboxStatsQ = useQuery({
    queryKey: ['email-inbox-stats'],
    queryFn: fetchEmailInboxStats,
    refetchInterval: 5 * 60 * 1000,
    retry: false,
  })
  const pendingCount = inboxStatsQ.data?.pending ?? 0

  return (
    <div className="flex min-h-screen">
      {fileUploadBusy ? (
        <div className="pointer-events-none fixed left-0 right-0 top-0 z-[100]">
          <IndeterminateProgressBar />
        </div>
      ) : null}
      <aside className="flex w-56 shrink-0 flex-col border-r border-[var(--color-border-subtle)] bg-white">
        <div className="border-b border-[var(--color-border-subtle)] px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
            Personal Finance OS
          </p>
          <p className="mt-0.5 text-sm text-zinc-600">Local dashboard</p>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 p-2">
          {NAV.map((item) => {
            const Icon = item.icon
            const isInbox = item.to === '/email-inbox'
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  [
                    'flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-emerald-50 text-emerald-900'
                      : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900',
                  ].join(' ')
                }
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                <span className="flex-1">{item.label}</span>
                {isInbox && pendingCount > 0 && (
                  <span className="rounded-full bg-orange-100 px-1.5 py-0.5 text-xs font-semibold text-orange-700">
                    {pendingCount}
                  </span>
                )}
              </NavLink>
            )
          })}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
