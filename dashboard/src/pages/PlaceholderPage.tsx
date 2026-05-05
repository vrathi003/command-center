import { useLocation } from 'react-router-dom'

import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'

const TITLES: Record<string, string> = {
  '/budget': 'Budget',
  '/debt': 'Debt',
  '/investments': 'Investments',
  '/net-worth': 'Net worth',
  '/goals': 'Goals',
  '/income': 'Income & tax',
  '/reports': 'Reports',
  '/settings': 'Settings',
}

export function PlaceholderPage() {
  const { pathname } = useLocation()
  const title = TITLES[pathname] ?? 'Page'

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Placeholder"
        title={title}
        description="This section will be wired to the API in a later phase of the build plan."
      />
      <Panel variant="muted" className="text-center text-sm text-zinc-600">
        <p>
          Route <code className="rounded bg-zinc-200/60 px-1.5 py-0.5 font-mono text-xs">{pathname}</code>
        </p>
      </Panel>
    </div>
  )
}
