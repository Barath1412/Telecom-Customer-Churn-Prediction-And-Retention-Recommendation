import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import { Card, StatTile } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/States'
import { pct, usd, usdCompact } from '@/lib/format'

export function DashboardPage() {
  const { data, isPending, error, refetch } = useQuery({
    queryKey: qk.summary(),
    queryFn: api.summary,
  })
  if (isPending) return <Skeleton className="h-96 w-full" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />

  const funnel = [
    { stage: 'Scored', n: data.funnel.scored },
    { stage: 'Involuntary', n: data.funnel.involuntary },
    { stage: 'No offer', n: data.funnel.no_eligible_offer },
    { stage: 'Recommended', n: data.funnel.recommended },
    { stage: 'Queued', n: data.funnel.queued_today },
  ]
  const lift = data.precision_at_capacity / data.base_rate

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          label="Precision at capacity"
          value={pct(data.precision_at_capacity)}
          hint={`${lift.toLocaleString('en-US', { maximumFractionDigits: 2 })}× the ${pct(
            data.base_rate,
          )} base rate`}
        />
        <StatTile label="Offer spend" value={usdCompact(data.economics.offer_spend)} />
        <StatTile
          label="Expected value"
          value={usdCompact(data.economics.expected_value)}
          hint="assumption-based — not measured"
        />
        <StatTile
          label="Held back (control)"
          value={String(data.funnel.control)}
          hint="never contacted"
        />
      </div>

      <Card title="Decision funnel" subtitle="Every customer scored in this run">
        {/* Explicit height: ResponsiveContainer needs a bounded parent or it
            collapses to zero and renders nothing. */}
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={funnel} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#dedcd6" vertical={false} />
              <XAxis dataKey="stage" tick={{ fontSize: 12 }} stroke="#78776f" />
              <YAxis tick={{ fontSize: 12 }} stroke="#78776f" width={48} />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 7, border: '1px solid #dedcd6' }}
              />
              <Bar dataKey="n" radius={[3, 3, 0, 0]}>
                {funnel.map((d) => (
                  <Cell key={d.stage} fill={d.stage === 'Queued' ? '#2a78d6' : '#c2c0b8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        {/* Charts are decorative for assistive tech; the table is the real content. */}
        <table className="mt-3 w-full text-xs">
          <caption className="sr-only">Decision funnel counts</caption>
          <tbody>
            {funnel.map((f) => (
              <tr key={f.stage} className="border-b border-line last:border-0">
                <th scope="row" className="py-1 text-left font-normal text-ink-2">
                  {f.stage}
                </th>
                <td className="num py-1 text-right">{f.n.toLocaleString('en-US')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card
        title="Allocation parity"
        subtitle="Who receives offers, and of what value — not score parity"
      >
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-line-strong text-left text-ink-2">
              <th scope="col" className="py-1">Attribute</th>
              <th scope="col">Group</th>
              <th scope="col" className="text-right">n</th>
              <th scope="col" className="text-right">Queued</th>
              <th scope="col" className="text-right">Rate</th>
              <th scope="col" className="text-right">Mean offer value</th>
            </tr>
          </thead>
          <tbody>
            {data.allocation_parity.map((r) => (
              <tr key={`${r.attribute}-${r.group}`} className="border-b border-line last:border-0">
                <td className="py-1">{r.attribute}</td>
                <td>{r.group}</td>
                <td className="num text-right">{r.n}</td>
                <td className="num text-right">{r.queued}</td>
                <td className="num text-right">{pct(r.queue_rate, 2)}</td>
                <td className="num text-right">{usd(r.mean_offer_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}
