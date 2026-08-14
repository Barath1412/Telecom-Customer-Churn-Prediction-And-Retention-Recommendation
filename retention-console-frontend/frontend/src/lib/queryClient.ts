import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'

/**
 * Retry policy is the part people get wrong. A 4xx is a contract problem —
 * retrying it three times just delays the error the agent needs to see. Only
 * transient failures are retried.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false
        return failureCount < 2
      },
    },
    mutations: { retry: 0 },
  },
})

export const qk = {
  queue: (page: number) => ['queue', page] as const,
  customer: (id: string) => ['customer', id] as const,
  summary: () => ['summary'] as const,
  catalog: () => ['catalog'] as const,
}
