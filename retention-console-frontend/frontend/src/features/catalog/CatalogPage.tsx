import { useCatalog } from './useCatalog'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ErrorState'
import { deltaWithRange, months, pct, usd } from '@/lib/format'

export function CatalogPage() {
  const { data, isPending, error, refetch } = useCatalog()

  if (isPending) return <Skeleton className="h-96 w-full" label="Loading catalog" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />

  return (
    <div className="space-y-4">
      <Card title="Policy thresholds" subtitle={`Catalog v${data.catalog_version}`}>
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5 text-xs">
          <div>
            <dt className="text-ink-3">Margin floor</dt>
            <dd className="num mt-0.5 font-medium">{pct(data.policy.margin_floor_pct, 0)}</dd>
          </div>
          <div>
            <dt className="text-ink-3">Max discount</dt>
            <dd className="num mt-0.5 font-medium">{pct(data.policy.max_discount_pct, 0)}</dd>
          </div>
          <div>
            <dt className="text-ink-3">Cooldown</dt>
            <dd className="num mt-0.5 font-medium">{data.policy.cooldown_days} days</dd>
          </div>
          <div>
            <dt className="text-ink-3">Max offers / quarter</dt>
            <dd className="num mt-0.5 font-medium">{data.policy.max_offers_per_quarter}</dd>
          </div>
          <div>
            <dt className="text-ink-3">Approval required above</dt>
            <dd className="num mt-0.5 font-medium">{usd(data.policy.approval_required_above_cost)}</dd>
          </div>
        </dl>
      </Card>

      <Card title="Offer catalog" subtitle="Standard retention offers and policy constraints">
        <ul className="divide-y divide-line">
          {data.offers.map((o) => (
            <li key={o.offer_id} className="py-4 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm font-semibold">{o.name}</span>
                <span className="num font-mono text-xs text-ink-3" title={o.offer_id}>
                  {o.offer_id}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-2">
                <span>
                  Cost:{' '}
                  <strong className="num font-semibold text-ink">
                    {o.unit_cost !== null ? usd(o.unit_cost) : `${pct(o.discount_pct, 0)} of annual`}
                  </strong>
                </span>
                <span>·</span>
                <span>
                  Effect:{' '}
                  <strong className="num font-semibold text-ink">
                    {deltaWithRange(o.delta_prior, o.delta_ci)}
                  </strong>
                </span>
                <span>·</span>
                <span className="text-ink-3">Source: {o.delta_source ?? 'unsourced'}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 text-micro text-ink-3">
                <span>Requires: {o.requires_levers.join(', ') || 'none'}</span>
                {o.excludes_levers.length > 0 && (
                  <span>· Excludes: {o.excludes_levers.join(', ')}</span>
                )}
                <span>· Min tenure: {months(o.min_tenure_months)}</span>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}
