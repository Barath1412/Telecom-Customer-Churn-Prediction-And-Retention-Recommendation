import { Badge, type BadgeTone } from './ui/Badge'
import { pct } from '@/lib/format'
import type { RiskBand } from '@/types/api'

const TONE: Record<RiskBand, BadgeTone> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
}

/**
 * Colour is never the only carrier of the risk level — the band word is always
 * present. Roughly 1 in 12 men cannot reliably separate our high/critical reds.
 */
export function RiskBadge({ band, p }: { band: RiskBand; p: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="num text-sm font-semibold">{pct(p)}</span>
      <Badge tone={TONE[band]}>{band}</Badge>
    </span>
  )
}
