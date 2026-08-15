import { cn } from '@/lib/cn'
import type { Lever } from '@/types/api'

export interface LeverChipsProps {
  levers: Lever[]
  max?: number
  className?: string
}

export function LeverChips({ levers, max = 3, className }: LeverChipsProps) {
  const shown = levers.slice(0, max)
  const rest = levers.length - shown.length
  return (
    <ul className={cn('flex gap-1', className ?? 'flex-wrap')}>
      {shown.map((l) => (
        <li
          key={l.code}
          className="rounded border border-line bg-raised px-1.5 py-[1px] text-micro text-ink-2"
          title={l.code}
        >
          {l.label}
        </li>
      ))}
      {rest > 0 && (
        <li className="px-1 text-micro text-ink-3">
          +{rest} more
          <span className="sr-only">
            : {levers.slice(max).map((l) => l.label).join(', ')}
          </span>
        </li>
      )}
    </ul>
  )
}
