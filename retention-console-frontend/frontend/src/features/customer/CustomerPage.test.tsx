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

  it('handles control-arm customer without action bar or generate button and renders control notices', async () => {
    const controlCustomer = {
      ...detail,
      customer_id: '9465-RWMXL',
      arm: 'control' as const,
      narration: null,
    }
    server.use(
      http.get('/api/customers/:id', () => HttpResponse.json(controlCustomer)),
    )

    renderApp(<CustomerPage customerId="9465-RWMXL" />)
    await waitFor(() => expect(screen.getByText('9465-RWMXL')).toBeInTheDocument())

    // Recommendation card subtitle includes withheld note
    expect(
      screen.getByText(/Tech Support \+ Online Security bundle, 12 months — withheld, control group/i),
    ).toBeInTheDocument()

    // Note under EV breakdown
    expect(
      screen.getByText(/This customer is in the control group\. This is what the model would recommend/i),
    ).toBeInTheDocument()

    // Static bar instead of ActionBar
    expect(screen.getByText(/No action available — control group\./i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit offer' })).not.toBeInTheDocument()

    // Narration panel shows control group message, not Generate button
    expect(
      screen.getByText(/No note generated — control group, not contacted\./i),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /generate note/i })).not.toBeInTheDocument()
  })

  it('renders top 2 alternatives with talk_track text for treatment-arm customer', async () => {
    const customerWithAlts = {
      ...detail,
      alternatives: [
        {
          offer_id: 'OFF-CONTRACT-1Y',
          offer_name: '1-year contract at 10% off',
          cost: 65.0,
          delta_prior: 0.12,
          delta_ci: [0.04, 0.2] as [number, number],
          expected_value: 593.75,
          talk_track:
            'Alternative: 1-year contract at 10% off — costs $65.00, expected value $593.75. Present this if the customer declines the primary offer.',
        },
        {
          offer_id: 'OFF-TECHSUP-12',
          offer_name: 'Tech Support bundled free for 12 months',
          cost: 35.0,
          delta_prior: 0.08,
          delta_ci: [0.02, 0.15] as [number, number],
          expected_value: 411.84,
          talk_track:
            'Alternative: Tech Support bundled free for 12 months — costs $35.00, expected value $411.84. Present this if the customer declines the primary offer.',
        },
      ],
    }
    server.use(
      http.get('/api/customers/:id', () => HttpResponse.json(customerWithAlts)),
    )

    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    expect(screen.getByText('Alternative Offers')).toBeInTheDocument()
    expect(screen.getByText('1-year contract at 10% off')).toBeInTheDocument()
    expect(screen.getByText('Tech Support bundled free for 12 months')).toBeInTheDocument()
    expect(
      screen.getByText(/Alternative: 1-year contract at 10% off — costs \$65\.00, expected value \$593\.75\./i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Alternative: Tech Support bundled free for 12 months — costs \$35\.00, expected value \$411\.84\./i),
    ).toBeInTheDocument()
  })

  it('clicking "Present this instead" on second alternative preselects it in ConfirmDialog and submits modified_offer_id', async () => {
    const user = userEvent.setup()
    let actionPayload: unknown = null

    server.use(
      http.post('/api/customers/:id/action', async ({ request }) => {
        actionPayload = await request.json()
        return HttpResponse.json(actionFixture.response_example)
      }),
    )

    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    const presentButtons = screen.getAllByRole('button', { name: /select this offer/i })
    expect(presentButtons.length).toBeGreaterThanOrEqual(2)

    // Select the second alternative (OFF-TECHSUP-12 in standard detail fixture)
    await user.click(presentButtons[1]!)

    // Click Approve on ActionBar to open confirmation modal for the selected alternative
    await user.click(screen.getByRole('button', { name: /^approve$/i }))

    const modal = screen.getByRole('dialog', { name: /change the offer/i })
    expect(modal).toBeInTheDocument()

    // Confirm that the second alternative is pre-selected in the replacement offer select dropdown (NOT alternatives[0])
    const offerSelect = screen.getByRole('combobox', { name: /replacement offer/i })
    expect(offerSelect).toHaveValue('OFF-TECHSUP-12')

    // Submit confirmation
    await user.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    expect(actionPayload).toEqual({
      action: 'edit',
      actor: 'agent_42',
      reason_code: null,
      modified_offer_id: 'OFF-TECHSUP-12',
      note: null,
    })
  })

  it('swaps closing talk track line in Agent Note when alternate is selected and reverts with "Use recommended offer"', async () => {
    const customerWithAlts = {
      ...detail,
      alternatives: [
        {
          offer_id: 'OFF-CONTRACT-1Y',
          offer_name: '1-year contract at 10% off',
          cost: 65.0,
          delta_prior: 0.12,
          delta_ci: [0.04, 0.2] as [number, number],
          expected_value: 593.75,
          talk_track:
            'Alternative: 1-year contract at 10% off — costs $65.00, expected value $593.75. Present this if the customer declines the primary offer.',
        },
        {
          offer_id: 'OFF-TECHSUP-12',
          offer_name: 'Tech Support bundled free for 12 months',
          cost: 35.0,
          delta_prior: 0.08,
          delta_ci: [0.02, 0.15] as [number, number],
          expected_value: 411.84,
          talk_track:
            'Alternative: Tech Support bundled free for 12 months — costs $35.00, expected value $411.84. Present this if the customer declines the primary offer.',
        },
      ],
    }
    server.use(
      http.get('/api/customers/:id', () => HttpResponse.json(customerWithAlts)),
    )

    const user = userEvent.setup()
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    const originalTalkTrack = detail.narration.talk_track
    const originalSummary = detail.narration.summary
    const originalWhy = detail.narration.why
    const originalUncertainty = detail.narration.uncertainty_note

    // Initially recommended offer is active
    expect(screen.getByText(originalTalkTrack)).toBeInTheDocument()
    expect(screen.getByText(originalSummary)).toBeInTheDocument()
    expect(screen.getByText(originalWhy)).toBeInTheDocument()
    expect(screen.getByText(originalUncertainty)).toBeInTheDocument()
    expect(
      screen.queryByText(/Offer line shown for the selected alternative/i),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /use recommended offer/i }),
    ).not.toBeInTheDocument()

    // Click "Select this offer" on the first alternative
    const selectButtons = screen.getAllByRole('button', { name: /select this offer/i })
    await user.click(selectButtons[0]!)

    // Swapped talk track is displayed in Agent Note blockquote (and on the alternative card) with caption
    const expectedAltTalkTrack =
      'Alternative: 1-year contract at 10% off — costs $65.00, expected value $593.75. Present this if the customer declines the primary offer.'
    expect(screen.getAllByText(expectedAltTalkTrack).length).toBe(2)
    expect(
      screen.getByText(/Offer line shown for the selected alternative — rest of the note is unchanged\./i),
    ).toBeInTheDocument()

    // Summary, why, and uncertainty_note remain unchanged
    expect(screen.getByText(originalSummary)).toBeInTheDocument()
    expect(screen.getByText(originalWhy)).toBeInTheDocument()
    expect(screen.getByText(originalUncertainty)).toBeInTheDocument()

    // Click "Use recommended offer" to revert
    const revertBtn = screen.getByRole('button', { name: /use recommended offer/i })
    expect(revertBtn).toBeInTheDocument()
    await user.click(revertBtn)

    // Reverted back to original
    expect(screen.getByText(originalTalkTrack)).toBeInTheDocument()
    expect(
      screen.queryByText(/Offer line shown for the selected alternative/i),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /use recommended offer/i }),
    ).not.toBeInTheDocument()
  })

  it('switching to a different customer resets selectedOfferId back to new customer recommended offer', async () => {
    const user = userEvent.setup()
    const { rerender } = renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    // Select alternative on 0295-PPHDO
    const selectButtons = screen.getAllByRole('button', { name: /select this offer/i })
    await user.click(selectButtons[0]!)

    expect(
      screen.getByText(/Offer line shown for the selected alternative/i),
    ).toBeInTheDocument()

    // Switch to another customer
    rerender(<CustomerPage customerId="5461-QKNTN" />)
    await waitFor(() => expect(screen.getByText('5461-QKNTN')).toBeInTheDocument())

    // Selected offer reset - no alternative caption or button
    expect(
      screen.queryByText(/Offer line shown for the selected alternative/i),
    ).not.toBeInTheDocument()
  })

  it('does not render Approve/Reject when actionable is false', async () => {
    server.use(
      http.get('/api/customers/:id', () =>
        HttpResponse.json({
          ...detail,
          customer_id: '1335-NTIUC',
          actionable: false,
        }),
      ),
    )
    renderApp(<CustomerPage customerId="1335-NTIUC" />)
    await waitFor(() => expect(screen.getByText('1335-NTIUC')).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
    expect(screen.getByText(/not in today's active queue yet/i)).toBeInTheDocument()
  })

  it('renders Decision Finalized banner for approved customer and hides alternative offers', async () => {
    server.use(
      http.get('/api/customers/:id', () =>
        HttpResponse.json({
          ...detail,
          customer_id: '0295-PPHDO',
          actionable: false,
          decision: {
            action: 'approve',
            actor: 'agent_lead',
            reason_code: null,
            note: null,
            acted_at: '2026-08-17T12:00:00Z',
            offered_offer_id: 'OFF-BUNDLE-ALL',
            offered_offer_name: 'Tech Support + Online Security bundle, 12 months',
            offer_changed: false,
          },
        }),
      ),
    )
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    expect(screen.getByText(/Decision Finalized/i)).toBeInTheDocument()
    expect(screen.getByText(/Approved — Agreed Offer:/i)).toBeInTheDocument()
    expect(screen.getByText(/agent_lead/i)).toBeInTheDocument()
    expect(screen.queryByText(/Alternative Offers/i)).not.toBeInTheDocument()
  })

  it('renders Decision Finalized banner for rejected customer with reason code', async () => {
    server.use(
      http.get('/api/customers/:id', () =>
        HttpResponse.json({
          ...detail,
          customer_id: '0295-PPHDO',
          actionable: false,
          decision: {
            action: 'reject',
            actor: 'agent_lead',
            reason_code: 'already_contacted',
            note: 'Customer contacted on Monday',
            acted_at: '2026-08-17T12:00:00Z',
            offered_offer_id: 'OFF-BUNDLE-ALL',
            offered_offer_name: 'Tech Support + Online Security bundle, 12 months',
            offer_changed: false,
          },
        }),
      ),
    )
    renderApp(<CustomerPage customerId="0295-PPHDO" />)
    await waitFor(() => expect(screen.getByText('0295-PPHDO')).toBeInTheDocument())

    expect(screen.getByText(/Decision Finalized/i)).toBeInTheDocument()
    expect(screen.getByText(/Rejected — Reason:/i)).toBeInTheDocument()
    expect(screen.getByText(/already_contacted/i)).toBeInTheDocument()
    expect(screen.getByText(/Customer contacted on Monday/i)).toBeInTheDocument()
  })
})
