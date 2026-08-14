import { useMemo, useState } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import { useNavigate } from 'react-router-dom'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { Badge } from '@/components/ui/Badge'
import { usd } from '@/lib/format'
import type { QueueItem } from '@/types/api'

const col = createColumnHelper<QueueItem>()

export function QueueTable({ items }: { items: QueueItem[] }) {
  const navigate = useNavigate()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'ev', desc: true }])

  const columns = useMemo(
    () => [
      col.accessor('rank', { header: '#', cell: (c) => <span className="num">{c.getValue()}</span> }),
      col.accessor('customer_id', {
        header: 'Customer',
        cell: (c) => <span className="font-mono text-xs">{c.getValue()}</span>,
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
      col.accessor((r) => r.recommendation.offer_name ?? '—', {
        id: 'offer',
        header: 'Recommended offer',
        cell: (c) => <span className="text-xs">{c.getValue()}</span>,
      }),
      col.accessor((r) => r.recommendation.cost, {
        id: 'cost',
        header: 'Cost',
        cell: (c) => <span className="num">{usd(c.getValue())}</span>,
      }),
      col.accessor((r) => r.recommendation.expected_value, {
        id: 'ev',
        header: 'Expected value',
        cell: (c) => <span className="num font-semibold">{usd(c.getValue())}</span>,
      }),
      col.accessor('levers', {
        header: 'Levers',
        enableSorting: false,
        cell: (c) => <LeverChips levers={c.getValue()} />,
      }),
      col.accessor('arm', {
        header: 'Arm',
        cell: (c) =>
          c.getValue() === 'control' ? (
            <Badge tone="warn">control — do not contact</Badge>
          ) : (
            <Badge>treatment</Badge>
          ),
      }),
    ],
    [],
  )

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
                        className="inline-flex items-center gap-1 rounded"
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
              onClick={() => navigate(`/customers/${row.original.customer_id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  navigate(`/customers/${row.original.customer_id}`)
                }
              }}
              className="cursor-pointer border-b border-line last:border-0 hover:bg-raised focus-visible:bg-raised"
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
