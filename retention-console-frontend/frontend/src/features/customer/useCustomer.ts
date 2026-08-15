import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'

export function useCustomer(id: string) {
  return useQuery({
    queryKey: qk.customer(id),
    queryFn: () => api.customer(id),
    enabled: !!id,
  })
}
