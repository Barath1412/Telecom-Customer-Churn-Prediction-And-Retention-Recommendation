import type { ReactNode } from 'react'
import { ApiError } from '@/lib/api'
import { Button } from './ui/Button'

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line-strong px-6 py-10 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mx-auto mt-1 max-w-prose text-sm text-ink-3">{body}</p>
    </div>
  )
}

/**
 * LEAKAGE_REJECTED gets its own treatment on purpose: it is not a user mistake,
 * it means an upstream system sent a quarantined field and somebody needs to be
 * told, not asked to try again.
 */
export function ErrorState({
  error,
  onRetry,
  children,
}: {
  error: unknown
  onRetry?: () => void
  children?: ReactNode
}) {
  const api = error instanceof ApiError ? error : null
  const leakage = api?.code === 'LEAKAGE_REJECTED'
  return (
    <div
      role="alert"
      className={`rounded-lg border px-5 py-4 ${leakage ? 'border-danger' : 'border-line-strong'}`}
    >
      <p className="text-sm font-semibold">
        {leakage ? 'Blocked: quarantined field received' : 'Something went wrong'}
      </p>
      <p className="mt-1 text-sm text-ink-2">{api?.message ?? 'Unexpected error.'}</p>
      {api && api.fields.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-ink-2">
          {api.fields.map((f) => (
            <li key={f.field}>
              <span className="font-mono">{f.field}</span> — {f.message}
            </li>
          ))}
        </ul>
      )}
      {api && (
        <p className="mt-2 text-micro text-ink-3">
          Reference <span className="font-mono">{api.body.request_id}</span>
        </p>
      )}
      {leakage ? (
        <p className="mt-2 text-micro text-ink-3">
          Do not retry. Report this reference to the data team.
        </p>
      ) : (
        onRetry && (
          <Button className="mt-3" size="sm" onClick={onRetry}>
            Try again
          </Button>
        )
      )}
      {children}
    </div>
  )
}
