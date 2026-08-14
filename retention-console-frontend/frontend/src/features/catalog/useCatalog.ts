import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'

export function useCatalog() {
  return useQuery({
    queryKey: qk.catalog(),
    queryFn: api.catalog,
  })
}
