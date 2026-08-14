import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'

export function useQueue(page = 1) {
  return useQuery({ queryKey: qk.queue(page), queryFn: () => api.queue(page) })
}
