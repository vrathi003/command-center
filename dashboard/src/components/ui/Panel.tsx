import type { ReactNode } from 'react'

const variants: Record<'default' | 'emerald' | 'muted' | 'table', string> = {
  default:
    'rounded-2xl border border-zinc-200/80 bg-white shadow-md shadow-zinc-900/5 ring-1 ring-zinc-900/[0.04]',
  emerald:
    'rounded-2xl border border-emerald-200/60 bg-gradient-to-br from-emerald-50/50 via-white to-white shadow-md shadow-emerald-900/5 ring-1 ring-emerald-900/[0.05]',
  muted: 'rounded-2xl border border-zinc-200/70 bg-zinc-50/40 shadow-sm ring-1 ring-zinc-900/[0.03]',
  table: 'overflow-hidden rounded-2xl border border-zinc-200/80 bg-white shadow-lg shadow-zinc-900/5 ring-1 ring-zinc-900/[0.04]',
}

type PanelProps = {
  variant?: keyof typeof variants
  className?: string
  children: ReactNode
  padding?: boolean
}

export function Panel({ variant = 'default', className = '', children, padding = true }: PanelProps) {
  return (
    <div className={[variants[variant], padding ? 'p-5' : '', className].filter(Boolean).join(' ')}>
      {children}
    </div>
  )
}
