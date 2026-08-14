import { cn } from '@/lib/cn'

/**
 * Skeletons match the shape of what is coming, not a generic grey box. A table
 * that collapses to one spinner and then reflows to 40 rows makes the page feel
 * slower than it is.
 */
export interface SkeletonProps {
  className?: string
  label?: string
}

export function Skeleton({ className, label }: SkeletonProps) {
  return (
    <div
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn('animate-pulse rounded bg-raised', className)}
    />
  )
}

export interface TableSkeletonProps {
  rows?: number
  label?: string
  className?: string
}

export function TableSkeleton({ rows = 8, label = 'Loading', className }: TableSkeletonProps) {
  return (
    <div role="status" aria-label={label} className={cn('space-y-2', className)}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  )
}
