export interface EmptyStateProps {
  title: string
  body: string
  className?: string
}

/**
 * Explains why it's empty, never renders a bare "No data".
 */
export function EmptyState({ title, body, className }: EmptyStateProps) {
  return (
    <div
      className={`rounded-lg border border-dashed border-line-strong px-6 py-10 text-center ${
        className ?? ''
      }`}
    >
      <p className="text-sm font-medium">{title}</p>
      <p className="mx-auto mt-1 max-w-prose text-sm text-ink-3">{body}</p>
    </div>
  )
}
