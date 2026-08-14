import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'

export function useSummary() {
  return useQuery({
    queryKey: qk.summary(),
    queryFn: api.summary,
  })
}
