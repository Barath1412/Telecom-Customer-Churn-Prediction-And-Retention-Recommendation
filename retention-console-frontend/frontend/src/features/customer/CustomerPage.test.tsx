import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import userEvent from '@testing-library/user-event'
import { CustomerPage } from './CustomerPage'
import { server } from '@/mocks/server'
import { renderApp, screen, waitFor } from '@/test/utils'
import detail from '@/mocks/fixtures/GET_customer_detail.json'
import noOffer from '@/mocks/fixtures/GET_customer_no_offer.json'
import actionFixture from '@/mocks/fixtures/POST_action.json'

describe('CustomerPage', () => {
  it('renders loading skeleton with accessible name', () => {
    server.use(
      http.get('/api/customers/:id', async () => {
        await new Promise((r) => setTimeout(r, 200))
        return HttpResponse.json(detail)
      }),
    )
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    expect(screen.getByRole('status', { name: /loading customer/i })).toBeInTheDocument()
  })

  it('renders customer detail from happy-path fixture', async () => {
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    // Risk badge
    expect(screen.getByText(/critical/i)).toBeInTheDocument()
    expect(screen.getAllByText(/99.0%/).length).toBeGreaterThan(0)

    // Recommendation card with EV Breakdown
    expect(screen.getByText('Tech Support + Online Security bundle, 12 months')).toBeInTheDocument()
    expect(screen.getByText('$705.82')).toBeInTheDocument()

    // Agent note (Narration)
    expect(screen.getByText(/Fibre customer one month in/i)).toBeInTheDocument()

    // Attribution
    expect(screen.getByText('Tenure Months = 1')).toBeInTheDocument()

    // Action buttons
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Edit offer' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled()
  })

  it('renders customer with no qualifying offer fixture with no-offer empty state', async () => {
    renderApp(<CustomerPage customerId={noOffer.customer_id} />)
    await waitFor(() => expect(screen.getByText(noOffer.customer_id)).toBeInTheDocument())

    // Empty state for recommendation
    expect(screen.getByText('No qualifying offer')).toBeInTheDocument()
    expect(
      screen.getByText(/No catalog offer matched this customer's levers/i),
    ).toBeInTheDocument()

    // Approve button disabled with visible reason
    const approveBtn = screen.getByRole('button', { name: 'Approve' })
    expect(approveBtn).toBeDisabled()
    expect(
      screen.getByText(/Approve is unavailable because no offer qualified/i),
    ).toBeInTheDocument()

    // Reject button remains enabled
    expect(screen.getByRole('button', { name: 'Reject' })).toBeEnabled()

    // Narration fallback
    expect(screen.getByText(/No note was generated for this customer/i)).toBeInTheDocument()
  })

  it('shows an actionable error instead of a blank page on failure', async () => {
    server.use(http.get('/api/customers/:id', () => new HttpResponse(null, { status: 500 })))
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('handles LEAKAGE_REJECTED error without retry affordance', async () => {
    server.use(
      http.get('/api/customers/:id', () =>
        HttpResponse.json(
          {
            error: {
              code: 'LEAKAGE_REJECTED',
              message: 'Quarantined feature detected',
              request_id: 'req_leakage_123',
            },
          },
          { status: 400 },
        ),
      ),
    )
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/Blocked: quarantined field received/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })

  it('confirmation modal names the customer and states irreversibility language', async () => {
    const user = userEvent.setup()
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Approve' }))

    const modal = screen.getByRole('dialog', { name: /approve recommendation/i })
    expect(modal).toBeInTheDocument()
    expect(
      screen.getByText(/This writes an audit record against 0295-PPHDO\. It cannot be undone\./i),
    ).toBeInTheDocument()
  })

  it('handles reject action with reason select and dynamic note requirement', async () => {
    const user = userEvent.setup()
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Reject' }))

    const modal = screen.getByRole('dialog', { name: /reject recommendation/i })
    expect(modal).toBeInTheDocument()

    const reasonSelect = screen.getByRole('combobox', { name: /reason/i })
    const noteLabel = screen.getByText(/^note/i)
    const noteInput = screen.getByRole('textbox', { name: /^note/i })

    // Initially "already_contacted" - note is not required (no asterisk on Note label)
    expect(reasonSelect).toHaveValue('already_contacted')
    expect(noteLabel.querySelector('span[aria-hidden="true"]')).toBeNull()

    // Change to "other" - asterisk should appear on Note label and note becomes required
    await user.selectOptions(reasonSelect, 'other')
    expect(noteLabel.querySelector('span[aria-hidden="true"]')).toHaveTextContent('*')

    // Submitting with empty note blocks and shows error
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/add a short note/i)

    // Type note and submit successfully
    await user.type(noteInput, 'Customer requested service cancellation at store.')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('handles edit action allowing alternative offer selection', async () => {
    const user = userEvent.setup()
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Edit offer' }))

    const modal = screen.getByRole('dialog', { name: /change the offer/i })
    expect(modal).toBeInTheDocument()

    const offerSelect = screen.getByRole('combobox', { name: /replacement offer/i })
    expect(offerSelect).toBeInTheDocument()
    expect(offerSelect).toHaveValue('OFF-CONTRACT-1Y')

    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('discards in-flight form draft when modal is closed/cancelled', async () => {
    const user = userEvent.setup()
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    // Open reject modal and type in a draft note
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    await user.type(screen.getByRole('textbox', { name: /^note/i }), 'Draft rejection note')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    // Reopen modal and verify draft was discarded
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    expect(screen.getByRole('textbox', { name: /^note/i })).toHaveValue('')
  })

  it('maps server-side fields errors onto form field error slots', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('/api/customers/:id/action', () =>
        HttpResponse.json(
          {
            error: {
              code: 'VALIDATION_ERROR',
              message: 'Validation failed',
              fields: [
                {
                  field: 'note',
                  message: 'Note must be at least 10 characters',
                },
              ],
              request_id: 'req_val_123',
            },
          },
          { status: 422 },
        ),
      ),
    )

    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await user.type(screen.getByRole('textbox', { name: /^note/i }), 'Short')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() =>
      expect(screen.getByText('Note must be at least 10 characters')).toBeInTheDocument(),
    )
  })

  it('guarantees no optimistic updates while mutation is pending', async () => {
    const user = userEvent.setup()
    let resolveAction!: (value: unknown) => void
    const actionPromise = new Promise((resolve) => {
      resolveAction = resolve
    })

    server.use(
      http.post('/api/customers/:id/action', async () => {
        await actionPromise
        return HttpResponse.json(actionFixture.response_example)
      }),
    )

    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    // Modal remains open and button is in loading state
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    const confirmBtn = screen.getByRole('button', { name: 'Confirm' })
    expect(confirmBtn).toHaveAttribute('aria-busy', 'true')

    // Resolve mutation
    resolveAction(true)

    // Closes only after server confirmation
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('announces mutation failures in the assertive live region on error', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('/api/customers/:id/action', () => new HttpResponse(null, { status: 500 })),
    )

    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: 'Approve' }))
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    // Assertive live region receives the error toast
    await waitFor(() => {
      const assertiveRegion = document.querySelector('[aria-live="assertive"]')
      expect(assertiveRegion).toHaveTextContent(/internal server error/i)
    })
  })

  it('passes axe accessibility checks on the page and on all modal states', async () => {
    const user = userEvent.setup()
    const { container } = renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    // Page level check
    const pageAxe = await axe(container)
    expect(pageAxe.violations).toEqual([])

    // Approve Modal check
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    const approveAxe = await axe(container)
    expect(approveAxe.violations).toEqual([])
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    // Edit Modal check
    await user.click(screen.getByRole('button', { name: 'Edit offer' }))
    const editAxe = await axe(container)
    expect(editAxe.violations).toEqual([])
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    // Reject Modal check
    await user.click(screen.getByRole('button', { name: 'Reject' }))
    const rejectAxe = await axe(container)
    expect(rejectAxe.violations).toEqual([])
  })
})
