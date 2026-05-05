import type { ReactNode } from 'react'

type PageHeroProps = {
  /** Small label above the title, e.g. "Transactions" */
  eyebrow?: string
  title: string
  description?: ReactNode
  /** Right side: month pickers, actions, etc. */
  actions?: ReactNode
}

export function PageHero({ eyebrow, title, description, actions }: PageHeroProps) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch lg:justify-between">
      <div className="relative min-w-0 flex-1 overflow-hidden rounded-2xl border border-emerald-200/50 bg-gradient-to-br from-emerald-50/90 via-white to-white px-6 py-6 shadow-lg shadow-emerald-900/5 ring-1 ring-emerald-900/[0.04]">
        <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-emerald-400/10 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-8 left-1/3 h-24 w-48 rounded-full bg-teal-300/10 blur-xl" />
        <div className="relative">
          {eyebrow ? (
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700/90">{eyebrow}</p>
          ) : null}
          <h1 className={`font-bold tracking-tight text-zinc-900 ${eyebrow ? 'mt-1 text-3xl' : 'text-3xl'}`}>
            {title}
          </h1>
          {description ? (
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-600">{description}</p>
          ) : null}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 flex-col justify-center gap-2 lg:max-w-sm">{actions}</div> : null}
    </div>
  )
}
