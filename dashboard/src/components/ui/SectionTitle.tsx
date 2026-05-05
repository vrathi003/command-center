import type { ReactNode } from 'react'

export function SectionTitle({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={['mb-4 flex items-center gap-3', className].filter(Boolean).join(' ')}>
      <span className="h-7 w-1 shrink-0 rounded-full bg-gradient-to-b from-emerald-500 to-emerald-600 shadow-sm shadow-emerald-600/30" />
      <h2 className="text-sm font-bold uppercase tracking-[0.14em] text-zinc-700">{children}</h2>
    </div>
  )
}
