import { createColumnHelper } from '@tanstack/react-table'
import { Link } from 'react-router-dom'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { Badge } from '@/components/ui/Badge'
import { deltaWithRange, usd } from '@/lib/format'
import type { QueueItem } from '@/types/api'

const col = createColumnHelper<QueueItem>()

export const columns = [
  col.accessor('queue_position', {
    header: '#',
    cell: (c) => <span className="num">{c.getValue()}</span>,
  }),
  col.accessor('customer_id', {
    header: 'Customer',
    cell: (c) => (
      <Link
        to={`/customers/${encodeURIComponent(c.getValue())}`}
        className="font-mono text-xs whitespace-nowrap hover:underline focus-visible:underline"
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
    header: 'Offer',
    cell: (c) => {
      const decision = c.row.original.decision
      if (decision) {
        if (decision.action === 'approve' || decision.action === 'edit') {
          return (
            <div className="space-y-0.5 text-xs">
              <span className="font-medium text-ink whitespace-nowrap">
                Approved — offered: {decision.offered_offer_name ?? c.getValue() ?? '—'}
              </span>
              {decision.offer_changed && (
                <p className="text-micro text-ink-3 italic whitespace-nowrap">
                  (agent changed from the model&apos;s original recommendation)
                </p>
              )}
            </div>
          )
        }
        if (decision.action === 'reject') {
          return (
            <div className="space-y-0.5 text-xs">
              <span className="font-medium text-ink whitespace-nowrap">
                Rejected — {decision.reason_code ?? 'no reason'}
              </span>
            </div>
          )
        }
      }

      const name = c.getValue()
      return name ? (
        <span className="text-xs whitespace-nowrap">{name}</span>
      ) : (
        <span className="text-xs text-ink-3 whitespace-nowrap">No eligible offer</span>
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
        <div className="flex items-baseline gap-1.5 whitespace-nowrap">
          <span className="num font-semibold">{usd(c.getValue())}</span>
          <span className="text-micro text-ink-3">
            {deltaWithRange(rec.delta_prior, rec.delta_ci)} · {rec.delta_source ?? 'unsourced'}
          </span>
        </div>
      )
    },
  }),
  col.accessor('levers', {
    header: 'Levers',
    enableSorting: false,
    cell: (c) => (
      <LeverChips
        levers={c.getValue()}
        max={1}
        className="flex-nowrap items-center whitespace-nowrap"
      />
    ),
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