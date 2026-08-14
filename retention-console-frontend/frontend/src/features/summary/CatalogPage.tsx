import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/States'
import { deltaWithRange, pct, usd } from '@/lib/format'

export function CatalogPage() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: qk.catalog(),
    queryFn: api.catalog,
  })
  if (isPending) return <Skeleton className="h-96 w-full" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />

  return (
    <div className="space-y-4">
      <Card title="Policy" subtitle={`Catalog v${data.catalog_version}`}>
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5 text-xs">
          {Object.entries(data.policy).map(([k, v]) => (
            <div key={k}>
              <dt className="text-ink-3">{k.replace(/_/g, ' ')}</dt>
              <dd className="num">{typeof v === 'number' && v < 1 ? pct(v, 0) : String(v)}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card title="Offers">
        <ul className="divide-y divide-line">
          {data.offers.map((o) => (
            <li key={o.offer_id} className="py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm font-medium">{o.name}</span>
                <span className="font-mono text-xs text-ink-3">{o.offer_id}</span>
              </div>
              <p className="mt-1 text-xs text-ink-2">
                Requires {o.requires_levers.join(', ') || 'nothing'} ·{' '}
                {o.unit_cost !== null ? usd(o.unit_cost) : `${pct(o.discount_pct, 0)} of annual`} ·{' '}
                {deltaWithRange(o.delta_prior, o.delta_ci)}
              </p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}
