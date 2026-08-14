import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export type BadgeTone = 'neutral' | 'critical' | 'high' | 'medium' | 'low' | 'info' | 'warn'

const TONE: Record<BadgeTone, string> = {
  neutral: 'border-line-strong text-ink-2',
  critical: 'border-critical text-critical',
  high: 'border-high text-high',
  medium: 'border-medium text-medium',
  low: 'border-low text-low',
  info: 'border-accent text-accent',
  warn: 'border-warn text-warn',
}

/**
 * Outline, not filled. Filled pills at four severity levels turn a dense table
 * into a colour chart and stop conveying urgency.
 */
export function Badge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: BadgeTone
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-[1px] text-micro uppercase tracking-wide',
        TONE[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
