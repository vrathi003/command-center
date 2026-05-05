/**
 * Indeterminate strip for long-running requests (e.g. PDF + LM Studio) — no real % without SSE.
 */
export function IndeterminateProgressBar({
  label,
  className = '',
}: {
  label?: string
  className?: string
}) {
  return (
    <div className={className}>
      <div
        className="h-1 w-full overflow-hidden rounded-full bg-zinc-200/90"
        role="progressbar"
        aria-busy="true"
        aria-label={label ?? 'Working'}
      >
        <div
          className="h-full w-2/5 rounded-full bg-emerald-600"
          style={{ animation: 'pf-indeterminate 1.2s ease-in-out infinite' }}
        />
      </div>
      {label ? <p className="mt-2 text-xs text-zinc-600">{label}</p> : null}
    </div>
  )
}
