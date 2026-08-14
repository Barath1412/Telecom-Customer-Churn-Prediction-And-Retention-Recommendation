import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

type Tone = 'success' | 'error' | 'info'
interface Toast {
  id: number
  tone: Tone
  message: string
}

const Ctx = createContext<{ notify: (tone: Tone, message: string) => void } | null>(null)

/**
 * aria-live region. `polite` for success, `assertive` for errors — an agent
 * mid-call should not be interrupted by "saved", but must be interrupted by
 * "that failed".
 */
export function NotifierProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const notify = useCallback((tone: Tone, message: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, tone, message }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000)
  }, [])
  const value = useMemo(() => ({ notify }), [notify])

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        <div aria-live="polite" aria-atomic="false" className="contents">
          {toasts
            .filter((t) => t.tone !== 'error')
            .map((t) => (
              <ToastCard key={t.id} toast={t} />
            ))}
        </div>
        <div aria-live="assertive" aria-atomic="false" className="contents">
          {toasts
            .filter((t) => t.tone === 'error')
            .map((t) => (
              <ToastCard key={t.id} toast={t} />
            ))}
        </div>
      </div>
    </Ctx.Provider>
  )
}

function ToastCard({ toast }: { toast: Toast }) {
  return (
    <div
      className={cn(
        'pointer-events-auto rounded-lg border bg-surface px-4 py-3 text-sm shadow-pop',
        toast.tone === 'error' && 'border-danger',
        toast.tone === 'success' && 'border-ok',
        toast.tone === 'info' && 'border-line-strong',
      )}
    >
      {toast.message}
    </div>
  )
}

export function useNotifier() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useNotifier must be used inside <NotifierProvider>')
  return ctx
}
