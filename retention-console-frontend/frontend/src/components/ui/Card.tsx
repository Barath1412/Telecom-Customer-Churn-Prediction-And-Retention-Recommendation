import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
}: {
  title?: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={cn('rounded-lg border border-line bg-surface shadow-card', className)}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-4 border-b border-line px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function StatTile({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="num text-xl font-semibold leading-tight">{value}</div>
      <div className="mt-1 text-xs text-ink-3">{label}</div>
      {hint && <div className="mt-1 text-micro text-ink-3">{hint}</div>}
    </div>
  )
}
