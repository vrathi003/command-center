import { KeyRound, Loader2 } from 'lucide-react'
import { useState } from 'react'

import { storeApiKey } from '@/lib/api'

async function verifyKey(key: string): Promise<boolean> {
  try {
    const res = await fetch('/api/settings', {
      headers: { Authorization: `Bearer ${key}` },
    })
    return res.ok
  } catch {
    return false
  }
}

interface LoginPageProps {
  onLogin: () => void
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [key, setKey] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = key.trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)

    const ok = await verifyKey(trimmed)
    setLoading(false)

    if (ok) {
      storeApiKey(trimmed)
      onLogin()
    } else {
      setError('Incorrect key. Check APP_SECRET_KEY in your .env file.')
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 p-4">
      <div className="w-full max-w-sm">
        {/* Logo / title */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex size-14 items-center justify-center rounded-2xl bg-emerald-600 shadow-lg">
            <KeyRound className="size-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-zinc-900">Personal Finance OS</h1>
          <p className="mt-1 text-sm text-zinc-500">Enter your access key to continue</p>
        </div>

        <form onSubmit={handleSubmit} className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-zinc-600">Access key</span>
            <input
              type="password"
              value={key}
              onChange={(e) => { setKey(e.target.value); setError(null) }}
              placeholder="••••••••••••••••"
              autoFocus
              autoComplete="current-password"
              className="rounded-lg border border-zinc-200 px-4 py-2.5 text-sm text-zinc-900 placeholder:text-zinc-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </label>

          {error && (
            <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading || !key.trim()}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Verifying…
              </>
            ) : (
              'Unlock'
            )}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-zinc-400">
          Set <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono">APP_SECRET_KEY</code> in
          your <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono">.env</code> file
        </p>
      </div>
    </div>
  )
}
