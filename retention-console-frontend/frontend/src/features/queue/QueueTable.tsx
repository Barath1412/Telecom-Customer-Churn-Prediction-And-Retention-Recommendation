import { useState } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import { useNavigate } from 'react-router-dom'
import { columns } from './columns'
import type { QueueItem } from '@/types/api'

export interface QueueTableProps {
  items: QueueItem[]
}

export function QueueTable({ items }: QueueTableProps) {
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'ev', desc: true }])

  const table = useReactTable({
    data: items,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
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
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              tabIndex={0}
              onClick={() => navigate(`/customers/${encodeURIComponent(row.original.customer_id)}`)}
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
  )
}
