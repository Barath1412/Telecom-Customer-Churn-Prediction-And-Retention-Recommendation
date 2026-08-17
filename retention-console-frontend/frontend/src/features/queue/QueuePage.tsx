import { useState } from 'react'
import { QueueTable } from './QueueTable'
import { CustomerSearch } from './CustomerSearch'
import { useQueue } from './useQueue'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StatTile } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import type { QueueStatusFilter } from '@/types/api'

export function QueuePage() {
  const [status, setStatus] = useState<QueueStatusFilter>('pending')
  const [page, setPage] = useState(1)
  const [globalFilter, setGlobalFilter] = useState('')

  const { data, isPending, error, refetch } = useQueue(page, 40, status)

  if (isPending) return <TableSkeleton rows={10} label="Loading queue" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />

  const activeTotal =
    status === 'pending'
      ? data.pending_total
      : status === 'approved'
        ? data.approved_total
        : data.rejected_total

  const totalPages = Math.max(1, Math.ceil(activeTotal / data.page_size))

  const handleStatusChange = (newStatus: QueueStatusFilter) => {
    setStatus(newStatus)
    setPage(1)
  }

  const activeCapacity = Math.min(data.pending_total, data.capacity)
  const backlogCount = Math.max(0, data.pending_total - data.capacity)

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <StatTile label="In queue tonight" value={String(activeCapacity)} />
        <StatTile label="Waiting behind today's 40" value={String(backlogCount)} />
        <StatTile label="Eligible overall" value={String(data.total_eligible)} />
        <StatTile label="Run" value={data.run_id.replace('run_', '')} hint="capacity-limited" />
      </div>

      <div
        role="tablist"
        aria-label="Queue status"
        className="flex items-center gap-2 border-b border-line pb-2"
      >
        <Button
          role="tab"
          aria-selected={status === 'pending'}
          variant={status === 'pending' ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => handleStatusChange('pending')}
        >
          Pending ({data.pending_total})
        </Button>
        <Button
          role="tab"
          aria-selected={status === 'approved'}
          variant={status === 'approved' ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => handleStatusChange('approved')}
        >
          Approved ({data.approved_total})
        </Button>
        <Button
          role="tab"
          aria-selected={status === 'rejected'}
          variant={status === 'rejected' ? 'primary' : 'ghost'}
          size="sm"
          onClick={() => handleStatusChange('rejected')}
        >
          Rejected ({data.rejected_total})
        </Button>
      </div>

      {data.items.length === 0 ? (
        <EmptyState
          title={
            status === 'approved'
              ? 'No approved customers'
              : status === 'rejected'
                ? 'No rejected customers'
                : "Nothing in tonight's queue"
          }
          body={
            status === 'approved'
              ? 'No customer recommendations have been approved yet.'
              : status === 'rejected'
                ? 'No customer recommendations have been rejected yet.'
                : 'No customer produced a positive-value, policy-approved offer.'
          }
        />
      ) : (
        <>
          <CustomerSearch value={globalFilter} onChange={setGlobalFilter} />
          <QueueTable
            items={data.items}
            globalFilter={globalFilter}
            onClearFilter={() => setGlobalFilter('')}
          />
          <div className="flex items-center justify-between border-t border-line pt-3 text-xs text-ink-2">
            <span>
              Page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}