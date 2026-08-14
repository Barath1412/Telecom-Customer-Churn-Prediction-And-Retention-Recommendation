import { QueueTable } from './QueueTable'
import { useQueue } from './useQueue'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { EmptyState, ErrorState } from '@/components/States'
import { StatTile } from '@/components/ui/Card'

export function QueuePage() {
  const { data, isPending, error, refetch } = useQueue(1)

  if (isPending) return <TableSkeleton rows={10} />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />
  if (data.items.length === 0)
    return (
      <EmptyState
        title="Nothing in tonight's queue"
        body="No customer produced a positive-value, policy-approved offer in this run."
      />
    )

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="In queue tonight" value={String(data.returned)} />
        <StatTile label="Eligible overall" value={String(data.total_eligible)} />
        <StatTile label="Run" value={data.run_id.replace('run_', '')} hint="capacity-limited" />
      </div>
      <QueueTable items={data.items} />
    </div>
  )
}
