import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import { PageError, PageLoading } from '@/components/ui/PageStatus'
import { PageHero } from '@/components/ui/PageHero'
import { Panel } from '@/components/ui/Panel'
import { SectionTitle } from '@/components/ui/SectionTitle'
import { fetchJournalEntry, fetchJournalRange, putJournalEntry } from '@/lib/api'

function formatLocalISODate(d: Date): string {
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${mo}-${day}`
}

/** Consecutive calendar days from `to` going back `count` days (inclusive of `to`). */
function buildDayList(toIso: string, count: number): string[] {
  const [ys, ms, ds] = toIso.split('-').map(Number)
  const out: string[] = []
  for (let i = 0; i < count; i += 1) {
    const d = new Date(ys, ms - 1, ds - i)
    out.push(formatLocalISODate(d))
  }
  return out
}

const DAYS_IN_SIDEBAR = 120

const markdownPreviewClass =
  'max-w-none space-y-3 text-sm text-zinc-800 [&_a]:text-emerald-700 [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-zinc-300 [&_blockquote]:pl-3 [&_blockquote]:text-zinc-600 [&_code]:rounded [&_code]:bg-zinc-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.85em] [&_h1]:text-lg [&_h1]:font-semibold [&_h2]:text-base [&_h2]:font-semibold [&_li]:my-0.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:leading-relaxed [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-zinc-900 [&_pre]:p-3 [&_pre]:text-zinc-100 [&_table]:w-full [&_table]:border-collapse [&_td]:border [&_td]:border-zinc-200 [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-zinc-200 [&_th]:bg-zinc-50 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_ul]:list-disc [&_ul]:pl-5'

type JournalEntrySectionProps = {
  selectedDate: string
}

/** Keyed by `selectedDate` on the parent so local edit state resets per day without an effect. */
function JournalEntrySection({ selectedDate }: JournalEntrySectionProps) {
  const queryClient = useQueryClient()
  const [typed, setTyped] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)

  const entryQuery = useQuery({
    queryKey: ['journal-entry', selectedDate],
    queryFn: () => fetchJournalEntry(selectedDate),
  })

  const baseline =
    entryQuery.status === 'success' ? (entryQuery.data === null ? '' : entryQuery.data.body) : ''

  const draftBody = dirty ? (typed ?? baseline) : baseline

  const saveMutation = useMutation({
    mutationFn: () => putJournalEntry(selectedDate, draftBody),
    onSuccess: () => {
      setDirty(false)
      setTyped(null)
      void queryClient.invalidateQueries({ queryKey: ['journal-entry', selectedDate] })
      void queryClient.invalidateQueries({ queryKey: ['journal-range'] })
    },
  })

  if (entryQuery.isError) {
    return (
      <PageError
        title="Could not load journal"
        message={<p className="text-sm">{String(entryQuery.error)}</p>}
      />
    )
  }

  if (entryQuery.isPending) {
    return <PageLoading lines={4} />
  }

  return (
    <div className="grid min-h-[320px] flex-1 grid-cols-1 gap-4 md:grid-cols-2 md:gap-5">
      <Panel className="flex min-h-0 flex-col p-4">
        <SectionTitle>Edit</SectionTitle>
        <textarea
          value={draftBody}
          onChange={(e) => {
            setTyped(e.target.value)
            setDirty(true)
          }}
          spellCheck
          className="mt-2 min-h-0 w-full flex-1 resize-none rounded-lg border border-zinc-200 bg-white p-3 font-mono text-sm text-zinc-900 outline-none ring-emerald-500/30 focus:ring-2"
          style={{ minHeight: 'min(50vh, 420px)' }}
          placeholder="Write markdown…"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!dirty || saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {saveMutation.isPending ? 'Saving…' : 'Save'}
          </button>
          {entryQuery.isFetching ? <span className="text-xs text-zinc-500">Syncing…</span> : null}
          {saveMutation.isError ? (
            <span className="text-xs text-red-600">{String(saveMutation.error)}</span>
          ) : null}
        </div>
      </Panel>

      <Panel className="flex min-h-0 flex-col p-4">
        <SectionTitle>Preview</SectionTitle>
        <div
          className={`mt-2 min-h-0 flex-1 overflow-y-auto rounded-lg border border-zinc-100 bg-zinc-50/80 p-3 ${markdownPreviewClass}`}
          style={{ minHeight: 'min(50vh, 420px)' }}
        >
          {draftBody.trim() === '' ? (
            <p className="text-sm text-zinc-500">Nothing to preview yet.</p>
          ) : (
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
              {draftBody}
            </ReactMarkdown>
          )}
        </div>
      </Panel>
    </div>
  )
}

function formatDateLabel(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d)
  const nowY = new Date().getFullYear()
  return dt.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(dt.getFullYear() !== nowY ? { year: 'numeric' as const } : {}),
  })
}

export function JournalPage() {
  const todayIso = useMemo(() => formatLocalISODate(new Date()), [])
  const [selectedDate, setSelectedDate] = useState(todayIso)

  const dayList = useMemo(() => {
    const base = buildDayList(todayIso, DAYS_IN_SIDEBAR)
    if (base.includes(selectedDate)) {
      return base
    }
    return [...new Set([selectedDate, ...base])].sort((a, b) => b.localeCompare(a))
  }, [todayIso, selectedDate])

  const { rangeFrom, rangeTo } = useMemo(() => {
    const sorted = [...dayList].sort((a, b) => a.localeCompare(b))
    return { rangeFrom: sorted[0]!, rangeTo: sorted[sorted.length - 1]! }
  }, [dayList])

  const markersQuery = useQuery({
    queryKey: ['journal-range', rangeFrom, rangeTo],
    queryFn: () => fetchJournalRange(rangeFrom, rangeTo),
  })

  const hasEntry = useMemo(() => {
    const s = new Set<string>()
    for (const row of markersQuery.data ?? []) {
      s.add(row.entry_date)
    }
    return s
  }, [markersQuery.data])

  return (
    <div className="space-y-6">
      <PageHero
        eyebrow="Journal"
        title="Daily notes"
        description="Pick a date in the list, write markdown, save. Empty days are removed on save."
      />

      <div className="flex flex-col gap-4 lg:flex-row lg:items-stretch">
        <aside className="w-full shrink-0 border border-[var(--color-border-subtle)] bg-white lg:w-52 lg:rounded-lg lg:border">
          <div className="border-b border-[var(--color-border-subtle)] p-3">
            <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500">
              Jump to date
            </label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => {
                const v = e.target.value
                if (v) setSelectedDate(v)
              }}
              className="mt-1.5 w-full rounded-md border border-zinc-200 px-2 py-1.5 text-sm text-zinc-900"
            />
          </div>
          {markersQuery.isError ? (
            <p className="p-3 text-xs text-amber-700">Markers: {String(markersQuery.error)}</p>
          ) : null}
          <div className="max-h-[min(70vh,520px)] overflow-y-auto p-1">
            <ul className="space-y-0.5">
              {dayList.map((iso) => {
                const selected = iso === selectedDate
                const dot = hasEntry.has(iso)
                return (
                  <li key={iso}>
                    <button
                      type="button"
                      onClick={() => setSelectedDate(iso)}
                      className={[
                        'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
                        selected
                          ? 'bg-emerald-50 font-medium text-emerald-900'
                          : 'text-zinc-700 hover:bg-zinc-50',
                      ].join(' ')}
                    >
                      <span
                        className={[
                          'h-1.5 w-1.5 shrink-0 rounded-full',
                          dot ? 'bg-emerald-500' : 'bg-zinc-200',
                        ].join(' ')}
                        aria-hidden
                      />
                      <span className="min-w-0 truncate">{formatDateLabel(iso)}</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <p className="mb-2 text-xs font-medium text-zinc-500">{selectedDate}</p>
          <JournalEntrySection key={selectedDate} selectedDate={selectedDate} />
        </div>
      </div>
    </div>
  )
}
