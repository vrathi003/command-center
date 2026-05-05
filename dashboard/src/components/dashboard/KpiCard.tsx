type KpiTone = 'spending' | 'balance' | 'neutral'

const toneClass: Record<KpiTone, string> = {
  spending:
    'border-l-[3px] border-l-emerald-500 bg-gradient-to-br from-emerald-50/60 via-white to-white shadow-md shadow-emerald-900/5 ring-1 ring-emerald-900/[0.06]',
  balance:
    'border-l-[3px] border-l-violet-500 bg-gradient-to-br from-violet-50/50 via-white to-white shadow-md shadow-violet-900/5 ring-1 ring-violet-900/[0.05]',
  neutral:
    'border-l-[3px] border-l-zinc-300 bg-gradient-to-br from-zinc-50/90 to-white shadow-md shadow-zinc-900/5 ring-1 ring-zinc-900/[0.04]',
}

type KpiCardProps = {
  label: string
  value: string
  hint?: string
  tone?: KpiTone
}

export function KpiCard({ label, value, hint, tone = 'neutral' }: KpiCardProps) {
  const valueNegative = value.trim().startsWith('-') || value.includes('−')
  return (
    <div
      className={[
        'group rounded-2xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg',
        toneClass[tone],
      ].join(' ')}
    >
      <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-zinc-500">{label}</p>
      <p
        className={[
          'mt-2 text-xl font-bold tabular-nums tracking-tight',
          valueNegative ? 'text-rose-700' : 'text-zinc-900',
        ].join(' ')}
      >
        {value}
      </p>
      {hint ? <p className="mt-2 text-xs leading-snug text-zinc-500">{hint}</p> : null}
    </div>
  )
}
