import { cn } from '@/lib/cn'

/**
 * Skeletons match the shape of what is coming, not a generic grey box. A table
 * that collapses to one spinner and then reflows to 40 rows makes the page feel
 * slower than it is.
 */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-raised', className)} aria-hidden="true" />
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading queue" className="space-y-2">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  )
}
