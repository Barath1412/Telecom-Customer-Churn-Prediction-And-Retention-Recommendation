import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  /** Shows a spinner and disables the button. Keeps width stable. */
  loading?: boolean
}

const VARIANT: Record<Variant, string> = {
  primary: 'bg-ink text-surface hover:bg-ink-2 border-ink',
  secondary: 'bg-surface text-ink hover:bg-raised border-line-strong',
  ghost: 'bg-transparent text-ink-2 hover:bg-raised border-transparent',
  danger: 'bg-surface text-danger hover:bg-raised border-danger/40',
}
const SIZE: Record<Size, string> = { sm: 'h-8 px-3 text-sm', md: 'h-9 px-4 text-sm' }

/**
 * Note there is no `disabled` styling that removes the element from the tab
 * order silently — a disabled Approve button with no explanation is the single
 * most common accessibility complaint in review tools. Pair it with a reason.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading = false, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      aria-busy={loading || undefined}
      disabled={rest.disabled || loading}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded border font-medium',
        'transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        VARIANT[variant],
        SIZE[size],
        className,
      )}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  )
})
