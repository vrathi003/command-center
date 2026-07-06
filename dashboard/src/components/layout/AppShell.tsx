import { useIsMutating, useQuery } from '@tanstack/react-query'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowLeftRight,
  Building2,
  CreditCard,
  FileDown,
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
  Store,
  Target,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { IndeterminateProgressBar } from '@/components/ui/IndeterminateProgressBar'
import { fetchEmailInboxStats } from '@/lib/api'

type NavItem = { to: string; label: string; icon: LucideIcon; end?: boolean }

type NavGroup = {
  label: string
  items: NavItem[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Money',
    items: [
      { to: '/accounts', label: 'Accounts', icon: Wallet },
      { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
      { to: '/merchants', label: 'Merchants', icon: Store },
      { to: '/budget', label: 'Budget', icon: PieChart },
    ],
  },
  {
    label: 'Import',
    items: [
      { to: '/statement-import', label: 'Statement import', icon: FileDown },
      { to: '/email-inbox', label: 'Gmail inbox', icon: Mail },
    ],
  },
  {
    label: 'Credit & debt',
    items: [
      { to: '/credit-cards', label: 'Credit cards', icon: CreditCard },
      { to: '/debt', label: 'Debt', icon: Landmark },
      { to: '/recurring', label: 'Subscriptions & EMIs', icon: Repeat },
    ],
  },
  {
    label: 'Wealth',
    items: [
      { to: '/investments', label: 'Investments', icon: TrendingUp },
      { to: '/net-worth', label: 'Net worth', icon: Scale },
      { to: '/goals', label: 'Goals', icon: Target },
      { to: '/income', label: 'Income & tax', icon: IndianRupee },
    ],
  },
  {
    label: 'Property & life',
    items: [
      { to: '/assets', label: 'Assets', icon: Building2 },
      { to: '/construction', label: 'Construction', icon: HardHat },
      { to: '/home', label: 'Home inventory', icon: House },
      { to: '/insurance', label: 'Insurance', icon: Shield },
    ],
  },
  {
    label: 'Insights',
    items: [
      { to: '/reports', label: 'Reports', icon: FileText },
      { to: '/journal', label: 'Journal', icon: NotebookPen },
    ],
  },
]

const OVERVIEW: NavItem = { to: '/', label: 'Overview', icon: LayoutDashboard, end: true }

function NavItemLink({
  item,
  badge,
}: {
  item: NavItem
  badge?: number
}) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end ?? item.to === '/'}
      className={({ isActive }) =>
        [
          'flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
          isActive
            ? 'bg-emerald-50 text-emerald-900'
            : 'text-zinc-600 hover:bg-zinc-50 hover:text-zinc-900',
        ].join(' ')
      }
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1 truncate">{item.label}</span>
      {badge !== undefined && badge > 0 ? (
        <span className="shrink-0 rounded-full bg-orange-100 px-1.5 py-0.5 text-xs font-semibold text-orange-700">
          {badge}
        </span>
      ) : null}
    </NavLink>
  )
}

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
        <div className="shrink-0 border-b border-[var(--color-border-subtle)] px-4 py-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
            Personal Finance OS
          </p>
          <p className="mt-0.5 text-sm text-zinc-600">Local dashboard</p>
        </div>

        <nav className="flex min-h-0 flex-1 flex-col overflow-y-auto p-2">
          <div className="mb-2">
            <NavItemLink item={OVERVIEW} />
          </div>

          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="mb-3 last:mb-0">
              <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
                {group.label}
              </p>
              <div className="flex flex-col gap-0.5">
                {group.items.map((item) => (
                  <NavItemLink
                    key={item.to}
                    item={item}
                    badge={item.to === '/email-inbox' ? pendingCount : undefined}
                  />
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="shrink-0 border-t border-[var(--color-border-subtle)] p-2">
          <NavItemLink item={{ to: '/settings', label: 'Settings', icon: Settings }} />
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6 lg:p-8">
        <Outlet />
      </main>
    </div>
  )
}
