import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { QueueTable } from './QueueTable'
import { CustomerSearch } from './CustomerSearch'
import { useQueue } from './useQueue'
import { UploadBatchModal } from './UploadBatchModal'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { StatTile } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { api } from '@/lib/api'
import type { QueueStatusFilter } from '@/types/api'

export function QueuePage() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<QueueStatusFilter>('pending')
  const [page, setPage] = useState(1)
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [uploadOpen, setUploadOpen] = useState(false)
  const [isResetting, setIsResetting] = useState(false)

  // Debounce search input so backend isn't queried on every character, and reset to page 1
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = searchQuery.trim()
      setDebouncedSearch(trimmed)
      setPage(1)
    }, 200)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const { data, isPending, error, refetch } = useQueue(page, 40, status, debouncedSearch)

  const handleResetDecisions = async () => {
    if (!window.confirm('Reset all decisions and return all customers to the Pending queue?')) return
    setIsResetting(true)
    try {
      await api.resetActions()
      await queryClient.invalidateQueries({ queryKey: ['queue'] })
      await queryClient.invalidateQueries({ queryKey: ['summary'] })
      setStatus('pending')
      setPage(1)
    } finally {
      setIsResetting(false)
    }
  }

  if (isPending) return <TableSkeleton rows={10} label="Loading queue" />
  if (error) return <ErrorState error={error} onRetry={() => void refetch()} />

  const activeTotal =
    data.cohort_total ?? (
      status === 'pending'
        ? data.pending_total
        : status === 'approved'
          ? data.approved_total
          : status === 'rejected'
            ? data.rejected_total
            : data.pending_total
    )

  const totalPages = Math.max(1, Math.ceil(activeTotal / data.page_size))

  const handleStatusChange = (newStatus: QueueStatusFilter) => {
    setStatus(newStatus)
    setPage(1)
  }

  const activeCapacity = Math.min(data.pending_total, data.capacity)
  const backlogCount = Math.max(0, data.pending_total - data.capacity)
  const isSearchActive = debouncedSearch.length > 0

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <StatTile label="Scored in run" value={String(data.total_scored ?? 1409)} hint="entire test cohort" />
        <StatTile label="Eligible for retention" value={String(data.pending_total)} hint={`of ${data.total_eligible} qualified`} />
        <StatTile label="In queue tonight" value={String(activeCapacity)} hint="active daily quota" />
        <StatTile label="Waiting in backlog" value={String(backlogCount)} hint="behind top 40" />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-2">
        <div
          role="tablist"
          aria-label="Queue status"
          className="flex items-center gap-2"
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

        <div className="flex items-center gap-2">
          {/* Reset Decisions button is strictly context-aware: only on Approved/Rejected tabs */}
          {(status === 'approved' || status === 'rejected') && (data.approved_total > 0 || data.rejected_total > 0) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleResetDecisions()}
              disabled={isResetting}
              className="text-xs text-ink-3 hover:text-ink border border-line"
            >
              <span>↺</span> {isResetting ? 'Resetting...' : 'Reopen Decisions'}
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-1.5"
          >
            <span>📁</span> Upload Batch (.xlsx / .csv)
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex-1 min-w-[240px]">
          <CustomerSearch value={searchQuery} onChange={setSearchQuery} />
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="cohort-select" className="text-xs text-ink-3">
            Cohort:
          </label>
          <select
            id="cohort-select"
            value={status}
            onChange={(e) => handleStatusChange(e.target.value as QueueStatusFilter)}
            className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-accent focus:outline-none"
          >
            <option value="pending">Eligible for Retention ({data.pending_total})</option>
            <option value="all_scored">All Scored Cohort ({data.total_scored ?? 1409})</option>
            <option value="no_action_needed">
              No Action Needed / Low Risk ({data.no_action_needed_total ?? 700})
            </option>
            <option value="review_no_profitable_offer">
              No Profitable Offer ({data.no_profitable_total ?? 18})
            </option>
            <option value="review_no_applicable_offer">
              No Applicable Offer ({data.no_applicable_total ?? 3})
            </option>
            <option value="approved">Approved ({data.approved_total})</option>
            <option value="rejected">Rejected ({data.rejected_total})</option>
          </select>
        </div>
      </div>

      {data.items.length === 0 ? (
        isSearchActive ? (
          <div className="space-y-3">
            <EmptyState
              title="No matching customer"
              body={`No customer in this cohort matches "${debouncedSearch}".`}
            />
            <div className="flex justify-center">
              <Button size="sm" variant="secondary" onClick={() => setSearchQuery('')}>
                Clear search
              </Button>
            </div>
          </div>
        ) : (
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
        )
      ) : (
        <>
          <QueueTable
            items={data.items}
            globalFilter={debouncedSearch}
            totalInCohort={activeTotal}
            onClearFilter={() => setSearchQuery('')}
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

      <UploadBatchModal open={uploadOpen} onClose={() => setUploadOpen(false)} />
    </div>
  )
}