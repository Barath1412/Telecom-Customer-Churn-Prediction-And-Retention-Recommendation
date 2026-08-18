import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { QueueStatusFilter } from '@/types/api'

export function useQueue(
  page = 1,
  pageSize = 40,
  status: QueueStatusFilter = 'pending',
  search = '',
) {
  return useQuery({
    queryKey: qk.queue(page, pageSize, status, search),
    queryFn: () => api.queue(page, pageSize, status, search),
  })
}