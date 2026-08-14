import type { Lever } from '@/types/api'

export function LeverChips({ levers, max = 3 }: { levers: Lever[]; max?: number }) {
  const shown = levers.slice(0, max)
  const rest = levers.length - shown.length
  return (
    <ul className="flex flex-wrap gap-1">
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
