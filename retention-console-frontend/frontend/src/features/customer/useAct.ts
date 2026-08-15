import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { useNotifier } from '@/components/ui/Notifier'
import type { ActionRequest } from '@/types/api'

/**
 * No optimistic update here, deliberately. Approving or rejecting an offer is a written
 * audit record; showing it as done before the server confirms would let an agent believe
 * an action was logged when it was not.
 */
export function useAct(id: string) {
  const qc = useQueryClient()
  const { notify } = useNotifier()

  return useMutation({
    mutationFn: (body: ActionRequest) => api.act(id, body),
    onSuccess: (res) => {
      notify('success', `${res.action} recorded — audit ${res.audit_id}`)
      void qc.invalidateQueries({ queryKey: qk.customer(id) })
      void qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (e: Error) => notify('error', e.message),
  })
}
