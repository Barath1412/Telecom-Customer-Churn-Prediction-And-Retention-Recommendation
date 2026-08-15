import { useState } from 'react'
import { QueueTable } from './QueueTable'
import { CustomerSearch } from './CustomerSearch'
import { useQueue } from './useQueue'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StatTile } from '@/components/ui/Card'

export function QueuePage() {
  const { data, isPending, error, refetch } = useQueue(1)
  const [globalFilter, setGlobalFilter] = useState('')

  if (isPending) return <TableSkeleton rows={10} label="Loading queue" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />
  if (data.items.length === 0)
    return (
      <EmptyState
        title="Nothing in tonight's queue"
        body="No customer produced a positive-value, policy-approved offer."
      />
    )

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <StatTile label="In queue tonight" value={String(data.returned)} />
        <StatTile label="Eligible overall" value={String(data.total_eligible)} />
        <StatTile label="Run" value={data.run_id.replace('run_', '')} hint="capacity-limited" />
      </div>
      <CustomerSearch value={globalFilter} onChange={setGlobalFilter} />
      <QueueTable
        items={data.items}
        globalFilter={globalFilter}
        onClearFilter={() => setGlobalFilter('')}
      />
    </div>
  )
}
