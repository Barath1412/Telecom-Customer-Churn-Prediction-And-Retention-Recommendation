import { useId, type InputHTMLAttributes, type SelectHTMLAttributes, type ReactNode } from 'react'
import { cn } from '@/lib/cn'

interface Base {
  label: string
  error?: string
  hint?: string
  required?: boolean
}

const shell =
  'w-full rounded border bg-surface px-3 py-2 text-sm placeholder:text-ink-3 ' +
  'disabled:opacity-50 aria-[invalid=true]:border-danger'

function Wrapper({
  id,
  label,
  hint,
  error,
  required,
  children,
}: Base & { id: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-ink-2">
        {label}
        {required && (
          <span className="ml-1 text-danger" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {children}
      {hint && !error && (
        <p id={`${id}-hint`} className="text-micro text-ink-3">
          {hint}
        </p>
      )}
      {/* role=alert so a screen reader announces the error the moment it appears,
          without the user having to navigate back to the field. */}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-micro text-danger">
          {error}
        </p>
      )}
    </div>
  )
}

export function TextField({
  label,
  hint,
  error,
  required,
  ...rest
}: Base & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId()
  return (
    <Wrapper id={id} label={label} hint={hint} error={error} required={required}>
      <input
        id={id}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={cn(shell, error ? 'border-danger' : 'border-line-strong')}
        {...rest}
      />
    </Wrapper>
  )
}

export function SelectField({
  label,
  hint,
  error,
  required,
  options,
  ...rest
}: Base &
  SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  const id = useId()
  return (
    <Wrapper id={id} label={label} hint={hint} error={error} required={required}>
      <select
        id={id}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        className={cn(shell, error ? 'border-danger' : 'border-line-strong')}
        {...rest}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Wrapper>
  )
}
