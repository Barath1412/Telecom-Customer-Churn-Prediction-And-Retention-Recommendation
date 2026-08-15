import { useEffect, useState } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type FilterFn,
  type SortingState,
} from '@tanstack/react-table'
import { useNavigate } from 'react-router-dom'
import { columns } from './columns'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/Button'
import type { QueueItem } from '@/types/api'

/**
 * Global filter intentionally matches customer_id only.
 * The columnId argument is ignored — all columns share this function
 * and a row passes if and only if its customer_id contains the search term.
 * Not branching on columnId avoids silent breakage if column definitions change.
 */
const customerIdFilter: FilterFn<QueueItem> = (row, _columnId, filterValue) => {
  const v = typeof filterValue === 'string' ? filterValue : String(filterValue)
  return row.original.customer_id.toLowerCase().includes(v.toLowerCase())
}

export interface QueueTableProps {
  items: QueueItem[]
  globalFilter: string
  onClearFilter: () => void
}

export function QueueTable({ items, globalFilter, onClearFilter }: QueueTableProps) {
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'ev', desc: true }])

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    globalFilterFn: customerIdFilter,
  })

  const filteredRows = table.getFilteredRowModel().rows
  const filteredCount = filteredRows.length

  // Amendment 1: keep the visible count instant but debounce the aria-live
  // announcement by 400 ms so a screen reader is not interrupted mid-word
  // while the agent is still typing.
  const [announcedCount, setAnnouncedCount] = useState(items.length)
  useEffect(() => {
    const id = setTimeout(() => {
      setAnnouncedCount(filteredCount)
    }, 400)
    return () => {
      clearTimeout(id)
    }
  }, [filteredCount])

  const isFiltered = globalFilter.length > 0

  return (
    <div className="space-y-3">
      {/* Visible count — updates instantly so the agent sees feedback immediately */}
      <p className="text-xs text-ink-3">{`Showing ${filteredCount} of ${items.length}`}</p>

      {/* Debounced aria-live region — always rendered (never unmounts) so count
          changes are announced even when the table is replaced by the empty state. */}
      <p aria-live="polite" className="sr-only" data-testid="count-announce">
        {`Showing ${announcedCount} of ${items.length}`}
      </p>

      {filteredCount === 0 && isFiltered ? (
        <div className="space-y-3">
          <EmptyState
            title="No matching customer"
            body={`No customer ID contains "${globalFilter}". Clear the search to see all ${items.length} customers.`}
          />
          <div className="flex justify-center">
            <Button size="sm" variant="secondary" onClick={onClearFilter}>
              Clear search
            </Button>
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">
              Tonight&apos;s retention queue, sorted by expected value. Select a row to open the
              customer.
            </caption>
            <thead>
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id}>
                  {hg.headers.map((h) => {
                    const sorted = h.column.getIsSorted()
                    return (
                      <th
                        key={h.id}
                        scope="col"
                        aria-sort={
                          !h.column.getCanSort()
                            ? undefined
                            : sorted === 'asc'
                              ? 'ascending'
                              : sorted === 'desc'
                                ? 'descending'
                                : 'none'
                        }
                        className="border-b border-line-strong px-3 py-2 text-left text-micro uppercase tracking-wide text-ink-2"
                      >
                        {h.column.getCanSort() ? (
                          <button
                            type="button"
                            onClick={h.column.getToggleSortingHandler()}
                            className="inline-flex items-center gap-1 rounded focus-visible:ring-2"
                          >
                            {flexRender(h.column.columnDef.header, h.getContext())}
                            <span aria-hidden="true">
                              {sorted === 'asc' ? '▲' : sorted === 'desc' ? '▼' : '↕'}
                            </span>
                          </button>
                        ) : (
                          flexRender(h.column.columnDef.header, h.getContext())
                        )}
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {filteredRows.map((row) => (
                <tr
                  key={row.id}
                  tabIndex={0}
                  onClick={() =>
                    navigate(`/customers/${encodeURIComponent(row.original.customer_id)}`)
                  }
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      navigate(`/customers/${encodeURIComponent(row.original.customer_id)}`)
                    }
                  }}
                  className="h-11 cursor-pointer border-b border-line last:border-0 hover:bg-raised focus-visible:bg-raised"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 align-middle">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
