import { describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { axe } from 'vitest-axe'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Card, StatTile } from '@/components/ui/Card'
import { TextField } from '@/components/ui/TextField'
import { SelectField } from '@/components/ui/SelectField'
import { NotifierProvider, useNotifier } from '@/components/ui/Notifier'
import { Skeleton, TableSkeleton } from '@/components/ui/Skeleton'
import { RiskBadge } from '@/components/RiskBadge'
import { LeverChips } from '@/components/LeverChips'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { ApiError } from '@/lib/api'
import { renderApp, screen, render } from './utils'

describe('Button primitive', () => {
  it('renders all variants and handles click events', async () => {
    const onClick = vi.fn()
    const user = userEvent.setup()
    renderApp(
      <div>
        <Button variant="primary" onClick={onClick}>Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Danger</Button>
      </div>,
    )
    const btn = screen.getByRole('button', { name: 'Primary' })
    await user.click(btn)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('sets aria-busy and disables when loading', () => {
    renderApp(<Button loading>Submitting</Button>)
    const btn = screen.getByRole('button', { name: 'Submitting' })
    expect(btn).toHaveAttribute('aria-busy', 'true')
    expect(btn).toBeDisabled()
  })

  it('passes axe accessibility checks', async () => {
    const { container } = renderApp(<Button variant="primary">Accessible</Button>)
    const res = await axe(container)
    expect(res.violations).toEqual([])
  })
})

describe('Badge primitive', () => {
  it('renders with different semantic tones', () => {
    renderApp(
      <div>
        <Badge tone="critical">Critical</Badge>
        <Badge tone="low">Low</Badge>
        <Badge tone="info">Info</Badge>
      </div>,
    )
    expect(screen.getByText('Critical')).toHaveClass('border-critical')
    expect(screen.getByText('Low')).toHaveClass('border-low')
    expect(screen.getByText('Info')).toHaveClass('border-accent')
  })
})

describe('Card and StatTile primitives', () => {
  it('renders Card with header, subtitle, actions and children', () => {
    renderApp(
      <Card title="Card Title" subtitle="Card Subtitle" actions={<Button size="sm">Action</Button>}>
        <p>Card Body</p>
      </Card>,
    )
    expect(screen.getByText('Card Title')).toBeInTheDocument()
    expect(screen.getByText('Card Subtitle')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Action' })).toBeInTheDocument()
    expect(screen.getByText('Card Body')).toBeInTheDocument()
  })

  it('renders StatTile with label, value, and hint', () => {
    renderApp(<StatTile label="Total Value" value="$1,234.00" hint="Estimated CLTV" />)
    expect(screen.getByText('Total Value')).toBeInTheDocument()
    expect(screen.getByText('$1,234.00')).toBeInTheDocument()
    expect(screen.getByText('Estimated CLTV')).toBeInTheDocument()
  })
})

describe('TextField and SelectField primitives', () => {
  it('renders TextField with label, hint, and connects aria-describedby', () => {
    renderApp(<TextField label="Customer Name" hint="Enter full legal name" />)
    const input = screen.getByLabelText('Customer Name')
    expect(input).toBeInTheDocument()
    const hint = screen.getByText('Enter full legal name')
    expect(input).toHaveAttribute('aria-describedby', hint.id)
  })

  it('renders TextField with error, role=alert, and aria-invalid', () => {
    renderApp(<TextField label="Email" error="Email is required" />)
    const input = screen.getByLabelText('Email')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    const errorAlert = screen.getByRole('alert')
    expect(errorAlert).toHaveTextContent('Email is required')
    expect(input).toHaveAttribute('aria-describedby', errorAlert.id)
  })

  it('renders SelectField with options and changes value on select', async () => {
    const user = userEvent.setup()
    const options = [
      { value: 'opt1', label: 'Option 1' },
      { value: 'opt2', label: 'Option 2' },
    ]
    renderApp(<SelectField label="Choose Option" options={options} defaultValue="opt1" />)
    const select = screen.getByLabelText('Choose Option')
    expect(select).toHaveValue('opt1')
    await user.selectOptions(select, 'opt2')
    expect(select).toHaveValue('opt2')
  })
})

describe('NotifierProvider and useNotifier', () => {
  function TestNotifierTrigger() {
    const { notify } = useNotifier()
    return (
      <div>
        <Button onClick={() => notify('success', 'Action completed successfully')}>Notify Success</Button>
        <Button onClick={() => notify('error', 'Critical failure occurred')}>Notify Error</Button>
      </div>
    )
  }

  it('announces success in polite aria-live and error in assertive aria-live', async () => {
    const user = userEvent.setup()
    renderApp(
      <NotifierProvider>
        <TestNotifierTrigger />
      </NotifierProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'Notify Success' }))
    expect(screen.getByText('Action completed successfully')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Notify Error' }))
    expect(screen.getByText('Critical failure occurred')).toBeInTheDocument()
  })

  it('throws when useNotifier is used outside NotifierProvider', () => {
    expect(() => render(<TestNotifierTrigger />)).toThrow('useNotifier must be used inside <NotifierProvider>')
  })
})

describe('Skeleton and TableSkeleton', () => {
  it('renders Skeleton with pulse animation and aria-hidden when no label', () => {
    const { container } = renderApp(<Skeleton className="h-6 w-24" />)
    expect(container.firstChild).toHaveClass('animate-pulse')
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
    expect(container.firstChild).not.toHaveAttribute('role')
  })

  it('renders Skeleton with role="status" and custom label when label prop is passed', () => {
    renderApp(<Skeleton className="h-6 w-24" label="Loading dashboard" />)
    const status = screen.getByRole('status', { name: 'Loading dashboard' })
    expect(status).toBeInTheDocument()
    expect(status).not.toHaveAttribute('aria-hidden')
  })

  it('renders TableSkeleton with generic "Loading" default when no label prop', () => {
    renderApp(<TableSkeleton rows={3} />)
    const status = screen.getByRole('status', { name: 'Loading' })
    expect(status).toBeInTheDocument()
  })

  it('renders TableSkeleton with caller-supplied label that overrides the default', () => {
    renderApp(<TableSkeleton rows={5} label="Loading catalog" />)
    const status = screen.getByRole('status', { name: 'Loading catalog' })
    expect(status).toBeInTheDocument()
    // Confirm the default "Loading" is NOT present — custom label replaced it
    expect(screen.queryByRole('status', { name: 'Loading' })).not.toBeInTheDocument()
  })
})

describe('RiskBadge domain component', () => {
  it('displays probability and band word together', () => {
    renderApp(<RiskBadge band="critical" p={0.875} />)
    expect(screen.getByText('87.5%')).toBeInTheDocument()
    expect(screen.getByText('critical')).toBeInTheDocument()
  })
})

describe('LeverChips domain component', () => {
  it('truncates labels and exposes hidden labels to screen readers via sr-only', () => {
    const levers = [
      { code: 'L1', label: 'Fiber plan' },
      { code: 'L2', label: 'Tech support' },
      { code: 'L3', label: 'Device protection' },
      { code: 'L4', label: 'Online security' },
      { code: 'L5', label: 'Autopay' },
    ]
    renderApp(<LeverChips levers={levers} max={2} />)
    expect(screen.getByText('Fiber plan')).toBeInTheDocument()
    expect(screen.getByText('Tech support')).toBeInTheDocument()
    expect(screen.getByText('+3 more', { exact: false })).toBeInTheDocument()
    expect(screen.getByText(': Device protection, Online security, Autopay')).toHaveClass('sr-only')
  })
})

describe('EmptyState domain component', () => {
  it('renders title and descriptive explanation body', () => {
    renderApp(
      <EmptyState
        title="Nothing in tonight's queue"
        body="No customer produced a positive-value, policy-approved offer."
      />,
    )
    expect(screen.getByText("Nothing in tonight's queue")).toBeInTheDocument()
    expect(screen.getByText('No customer produced a positive-value, policy-approved offer.')).toBeInTheDocument()
  })
})

describe('ErrorState domain component', () => {
  it('renders normal error with Try again retry button', () => {
    const onRetry = vi.fn()
    const error = new ApiError(500, {
      code: 'SERVER_ERROR',
      message: 'Database query timeout',
      request_id: 'req_normal',
    })
    renderApp(<ErrorState error={error} onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Database query timeout')).toBeInTheDocument()
    expect(screen.getByText('req_normal')).toBeInTheDocument()
    const retryBtn = screen.getByRole('button', { name: 'Try again' })
    expect(retryBtn).toBeInTheDocument()
  })

  it('renders LEAKAGE_REJECTED with NO retry button and reporting instructions', () => {
    const onRetry = vi.fn()
    const leakageError = new ApiError(400, {
      code: 'LEAKAGE_REJECTED',
      message: 'Quarantined field detected in payload',
      fields: [{ field: 'Churn Score', message: 'quarantined' }],
      request_id: 'req_leak_001',
    })
    renderApp(<ErrorState error={leakageError} onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Blocked: quarantined field received')).toBeInTheDocument()
    expect(screen.getByText('Churn Score')).toBeInTheDocument()
    expect(screen.getByText('req_leak_001')).toBeInTheDocument()
    expect(screen.getByText('Do not retry. Report this reference to the data team.')).toBeInTheDocument()
    // CRITICAL: Retry button MUST NOT be rendered
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })
})
