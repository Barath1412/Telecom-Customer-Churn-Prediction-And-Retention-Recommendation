import { createColumnHelper } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { Badge } from '@/components/ui/Badge'
import { deltaWithRange, usd } from '@/lib/format'
import type { QueueItem } from '@/types/api'

const col = createColumnHelper<QueueItem>()

export const columns = [
  col.accessor('rank', {
    header: '#',
    cell: (c) => <span className="num">{c.getValue()}</span>,
  }),
  col.accessor('customer_id', {
    header: 'Customer',
    cell: (c) => (
      <Link
        to={`/customers/${encodeURIComponent(c.getValue())}`}
        className="font-mono text-xs hover:underline focus-visible:underline"
        onClick={(e) => e.stopPropagation()}
      >
        {c.getValue()}
      </Link>
    ),
  }),
  col.accessor((r) => r.risk.p_churn, {
    id: 'risk',
    header: 'Risk',
    cell: (c) => <RiskBadge band={c.row.original.risk.risk_band} p={c.getValue()} />,
  }),
  col.accessor((r) => r.value.cltv, {
    id: 'cltv',
    header: 'CLTV',
    cell: (c) => <span className="num">{usd(c.getValue())}</span>,
  }),
  col.accessor((r) => r.recommendation.offer_name, {
    id: 'offer',
    header: 'Recommended offer',
    cell: (c) => {
      const name = c.getValue()
      return name ? (
        <span className="text-xs">{name}</span>
      ) : (
        <span className="text-xs text-ink-3">No eligible offer</span>
      )
    },
  }),
  col.accessor((r) => r.recommendation.cost, {
    id: 'cost',
    header: 'Cost',
    cell: (c) => <span className="num">{usd(c.getValue())}</span>,
  }),
  col.accessor((r) => r.recommendation.expected_value, {
    id: 'ev',
    header: 'Expected value',
    cell: (c) => {
      const rec = c.row.original.recommendation
      return (
        <div>
          <div className="num font-semibold">{usd(c.getValue())}</div>
          <div className="text-micro text-ink-3">
            {deltaWithRange(rec.delta_prior, rec.delta_ci)} · {rec.delta_source ?? 'unsourced'}
          </div>
        </div>
      )
    },
  }),
  col.accessor('levers', {
    header: 'Levers',
    enableSorting: false,
    cell: (c) => <LeverChips levers={c.getValue()} />,
  }),
  col.accessor('arm', {
    header: 'Arm',
    cell: (c) =>
      c.getValue() === 'control' ? (
        <Badge tone="neutral">control — do not contact</Badge>
      ) : (
        <Badge tone="neutral">treatment</Badge>
      ),
  }),
]
