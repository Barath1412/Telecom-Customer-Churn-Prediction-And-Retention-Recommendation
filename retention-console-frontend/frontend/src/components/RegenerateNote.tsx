import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Button } from './ui/Button'
import { api, ApiError } from '@/lib/api'
import type { NarrateResponse, Narration } from '@/types/api'

export interface RegenerateNoteProps {
  customerId: string
  onGenerated: (narration: Narration, meta: { elapsed_ms: number; provider: string }) => void
}

/**
 * Runs the real pipeline for one customer, live, and hands the result up.
 *
 * This is deliberately a separate component from NarrationPanel rather than a hook
 * inside it. `useMutation` requires a QueryClientProvider above it, and
 * NarrationPanel is rendered bare in its own unit tests — putting the hook there
 * would break tests that have nothing to do with this feature. Here, the component
 * only mounts when a customerId is passed, so those tests never reach it.
 *
 * The elapsed counter is not decoration. A model call takes 5–15 seconds; a static
 * spinner for that long is indistinguishable from a hang, and someone watching over
 * your shoulder will assume it has crashed.
 */
export function RegenerateNote({ customerId, onGenerated }: RegenerateNoteProps) {
  const [seconds, setSeconds] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const mutation = useMutation<NarrateResponse, ApiError>({
    mutationFn: () => api.narrate(customerId, { force: true }),
    onSuccess: (data) =>
      onGenerated(data.narration, { elapsed_ms: data.elapsed_ms, provider: data.provider }),
  })

  const running = mutation.isPending

  useEffect(() => {
    if (running) {
      setSeconds(0)
      timer.current = setInterval(() => setSeconds((s) => s + 1), 1000)
    } else if (timer.current) {
      clearInterval(timer.current)
      timer.current = null
    }
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [running])

  return (
    <div className="space-y-2">
      <Button
        variant="primary"
        size="sm"
        loading={running}
        onClick={() => mutation.mutate()}
        aria-label={running ? 'Generating note' : 'Generate note with AI'}
      >
        {running ? `Generating… ${seconds}s` : 'Generate note with AI'}
      </Button>

      {running && (
        <p className="text-micro text-ink-3" role="status">
          Running the pipeline: score → levers → offer → evidence → model → six validators.
          This normally takes 5–15 seconds.
        </p>
      )}

      {mutation.isError && (
        <p className="text-micro text-danger" role="alert">
          {mutation.error instanceof ApiError
            ? `${mutation.error.code}: ${mutation.error.message}`
            : 'Generation failed.'}{' '}
          The note below is unchanged — you can try again.
        </p>
      )}
    </div>
  )
}
