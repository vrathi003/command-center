/** Mutation meta for global toast handling (TanStack Query Register). */

export type MutationToastMeta = {
  /** Shown on success for important actions only. */
  successMessage?: string
  /** Skip global error toast (page handles it). */
  silent?: boolean
}

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: MutationToastMeta
  }
}

export {}
