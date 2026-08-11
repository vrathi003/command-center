import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Toaster, toast } from 'sonner'

import { formatErrorMessage } from '@/lib/apiError'
import '@/lib/toastPolicy'

const mutationCache = new MutationCache({
  onError: (error, _variables, _context, mutation) => {
    if (mutation.meta?.silent) return
    toast.error(formatErrorMessage(error))
  },
  onSuccess: (_data, _variables, _context, mutation) => {
    const message = mutation.meta?.successMessage
    if (message) {
      toast.success(message)
    }
  },
})

const client = new QueryClient({
  mutationCache,
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
    },
  },
})

export function QueryProvider({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      {children}
      <Toaster
        position="top-right"
        richColors
        closeButton
        toastOptions={{
          duration: 5000,
          classNames: {
            toast: 'font-sans',
          },
        }}
      />
    </QueryClientProvider>
  )
}
