import type { ReactNode } from 'react'

type PageLoadingProps = {
  /** Number of placeholder cards in the grid */
  lines?: number
  /** Extra tall block (e.g. chart / table area) */
  showFooterBlock?: boolean
}

export function PageLoading({ lines = 4, showFooterBlock = false }: PageLoadingProps) {
  const gridCols =
    lines >= 5
      ? 'sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5'
      : 'sm:grid-cols-2'
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-28 rounded-2xl bg-gradient-to-r from-zinc-200/80 to-zinc-100/80" />
      <div className={`grid gap-3 ${gridCols}`}>
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="h-24 rounded-2xl bg-zinc-100/90" />
        ))}
      </div>
      {showFooterBlock ? <div className="h-72 rounded-2xl bg-zinc-100/90" /> : null}
    </div>
  )
}

export function PageError({ title, message }: { title: string; message: ReactNode }) {
  return (
    <div className="rounded-2xl border border-red-200/80 bg-gradient-to-br from-red-50 to-white p-6 text-red-900 shadow-md">
      <p className="font-semibold">{title}</p>
      <div className="mt-2 text-sm">{message}</div>
    </div>
  )
}
