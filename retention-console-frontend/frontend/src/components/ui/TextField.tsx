import { useId, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  labelAccessory?: React.ReactNode
  error?: string
  hint?: string
  required?: boolean
}

export function TextField({
  label,
  labelAccessory,
  hint,
  error,
  required,
  className,
  ...rest
}: TextFieldProps) {
  const id = useId()
  const errorId = `${id}-error`
  const hintId = `${id}-hint`

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="block text-xs font-medium text-ink-2">
          {label}
          {required && (
            <span className="ml-1 text-danger" aria-hidden="true">
              *
            </span>
          )}
        </label>
        {labelAccessory}
      </div>
      <input
        id={id}
        aria-invalid={!!error}
        aria-describedby={error ? errorId : hint ? hintId : undefined}
        className={cn(
          'w-full rounded border bg-surface px-3 py-2 text-sm placeholder:text-ink-3',
          'disabled:opacity-50 aria-[invalid=true]:border-danger',
          error ? 'border-danger' : 'border-line-strong',
          className,
        )}
        required={required}
        {...rest}
      />
      {hint && !error && (
        <p id={hintId} className="text-micro text-ink-3">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} role="alert" className="text-micro text-danger">
          {error}
        </p>
      )}
    </div>
  )
}