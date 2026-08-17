import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import userEvent from '@testing-library/user-event'
import { ScorePage } from './ScorePage'
import { assertNoQuarantinedFields, LeakageGuardError } from './leakageGuard'
import { server } from '@/mocks/server'
import { renderApp, screen, waitFor } from '@/test/utils'
import scoreFixture from '@/mocks/fixtures/POST_score.json'

describe('ScorePage and Manual Scoring Form', () => {
  it('renders initial form with defaults and empty result state', () => {
    renderApp(<ScorePage />)
    expect(screen.getByRole('heading', { level: 1, name: /manual scoring/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /calculate score/i })).toBeInTheDocument()
    expect(screen.getByText(/no score calculated/i)).toBeInTheDocument()
  })

  it('Rule A: Internet Service === "No" forces all six add-ons to "No internet service" and disables them', async () => {
    const user = userEvent.setup()
    renderApp(<ScorePage />)

    const internetSelect = screen.getByRole('combobox', { name: /^internet service/i })
    await user.selectOptions(internetSelect, 'No')

    const addons = [
      'Online Security',
      'Online Backup',
      'Device Protection',
      'Tech Support',
      'Streaming TV',
      'Streaming Movies',
    ]

    for (const addon of addons) {
      const select = screen.getByRole('combobox', { name: new RegExp(`^${addon}`, 'i') })
      expect(select).toBeDisabled()
      expect(select).toHaveValue('No internet service')
    }
  })

  it('Rule B: Phone Service === "No" forces Multiple Lines to "No phone service" and disables it', async () => {
    const user = userEvent.setup()
    renderApp(<ScorePage />)

    const phoneSelect = screen.getByRole('combobox', { name: /^phone service/i })
    await user.selectOptions(phoneSelect, 'No')

    const multiLinesSelect = screen.getByRole('combobox', { name: /^multiple lines/i })
    expect(multiLinesSelect).toBeDisabled()
    expect(multiLinesSelect).toHaveValue('No phone service')
  })

  it('REVERSE: Internet "No" -> "DSL" resets all six add-ons to "No"', async () => {
    const user = userEvent.setup()
    renderApp(<ScorePage />)

    const internetSelect = screen.getByRole('combobox', { name: /^internet service/i })
    await user.selectOptions(internetSelect, 'No')

    // Transition back to DSL
    await user.selectOptions(internetSelect, 'DSL')

    const addons = [
      'Online Security',
      'Online Backup',
      'Device Protection',
      'Tech Support',
      'Streaming TV',
      'Streaming Movies',
    ]

    for (const addon of addons) {
      const select = screen.getByRole('combobox', { name: new RegExp(`^${addon}`, 'i') })
      expect(select).not.toBeDisabled()
      expect(select).toHaveValue('No')
    }
  })

  it('REVERSE: Phone "No" -> "Yes" resets Multiple Lines to "No"', async () => {
    const user = userEvent.setup()
    renderApp(<ScorePage />)

    const phoneSelect = screen.getByRole('combobox', { name: /^phone service/i })
    await user.selectOptions(phoneSelect, 'No')

    // Transition back to Yes
    await user.selectOptions(phoneSelect, 'Yes')

    const multiLinesSelect = screen.getByRole('combobox', { name: /^multiple lines/i })
    expect(multiLinesSelect).not.toBeDisabled()
    expect(multiLinesSelect).toHaveValue('No')
  })

  it('Rule A reverse when an add-on held "Yes" before transitions: unconditionally resets all six to "No"', async () => {
    const user = userEvent.setup()
    renderApp(<ScorePage />)

    const internetSelect = screen.getByRole('combobox', { name: /^internet service/i })
    await user.selectOptions(internetSelect, 'DSL')

    const techSupportSelect = screen.getByRole('combobox', { name: /^tech support/i })
    await user.selectOptions(techSupportSelect, 'Yes')
    expect(techSupportSelect).toHaveValue('Yes')

    // Switch to No
    await user.selectOptions(internetSelect, 'No')
    expect(techSupportSelect).toHaveValue('No internet service')
    expect(techSupportSelect).toBeDisabled()

    // Switch back to DSL -> all six must unconditionally read "No"
    await user.selectOptions(internetSelect, 'DSL')
    expect(techSupportSelect).toHaveValue('No')
    expect(techSupportSelect).not.toBeDisabled()

    const addons = [
      'Online Security',
      'Online Backup',
      'Device Protection',
      'Tech Support',
      'Streaming TV',
      'Streaming Movies',
    ]
    for (const addon of addons) {
      const select = screen.getByRole('combobox', { name: new RegExp(`^${addon}`, 'i') })
      expect(select).toHaveValue('No')
    }
  })

  it('leakageGuard rejects a payload containing a quarantined field', () => {
    expect(() => {
      assertNoQuarantinedFields({
        Gender: 'Male',
        CustomerID: '1234-ABCD',
      })
    }).toThrow(LeakageGuardError)

    expect(() => {
      assertNoQuarantinedFields({
        Gender: 'Female',
        'Monthly Charges': 50,
      })
    }).not.toThrow()
  })

  it('Server 400 VALIDATION_ERROR with fields[] renders inline field errors, not a toast', async () => {
    const user = userEvent.setup()
    server.use(
      http.post('/api/score', () =>
        HttpResponse.json(
          {
            error: {
              code: 'VALIDATION_ERROR',
              message: 'Invalid customer fields',
              fields: [
                { field: 'Monthly Charges', message: 'Monthly charges exceed allowed maximum for plan' },
              ],
              request_id: 'req_val_01',
            },
          },
          { status: 400 },
        ),
      ),
    )

    renderApp(<ScorePage />)
    const submitBtn = screen.getByRole('button', { name: /calculate score/i })
    await user.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText('Monthly charges exceed allowed maximum for plan')).toBeInTheDocument()
    })
    const monthlyInput = screen.getByRole('spinbutton', { name: /^monthly charges/i })
    expect(monthlyInput).toHaveAttribute('aria-invalid', 'true')
  })

  it('503 MODEL_UNAVAILABLE renders error alert and preserves form contents', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(
        '/api/score',
        () =>
          HttpResponse.json(
            {
              error: {
                code: 'MODEL_UNAVAILABLE',
                message: 'Inference engine is down',
                request_id: 'req_503',
              },
            },
            { status: 503 },
          ),
      ),
    )

    renderApp(<ScorePage />)
    const tenureInput = screen.getByRole('spinbutton', { name: /^tenure months/i })
    await user.clear(tenureInput)
    await user.type(tenureInput, '24')

    const submitBtn = screen.getByRole('button', { name: /calculate score/i })
    await user.click(submitBtn)

    await waitFor(() => {
      expect(
        screen.getByText(/model service is temporarily unavailable/i),
      ).toBeInTheDocument()
    })

    // Form value remains preserved
    expect(tenureInput).toHaveValue(24)
  })

  it('Total Charges consistency warning displays when inconsistent and still permits submit', async () => {
    const user = userEvent.setup()
    renderApp(<ScorePage />)

    const tenureInput = screen.getByRole('spinbutton', { name: /^tenure months/i })
    const monthlyInput = screen.getByRole('spinbutton', { name: /^monthly charges/i })
    const totalInput = screen.getByRole('spinbutton', { name: /^total charges/i })

    // Set tenure = 10, monthly = 100 -> product = 1000. Set total = 100 (inconsistent by >20%)
    await user.clear(tenureInput)
    await user.type(tenureInput, '10')

    await user.clear(monthlyInput)
    await user.type(monthlyInput, '100')

    await user.clear(totalInput)
    await user.type(totalInput, '100')

    expect(
      screen.getByText(/this doesn't match tenure x monthly charges/i),
    ).toBeInTheDocument()

    // Does not block submit
    const submitBtn = screen.getByRole('button', { name: /calculate score/i })
    await user.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText(/risk assessment/i)).toBeInTheDocument()
    })
  })

  it('cltv field is labelled as a business metric that does not affect p_churn', () => {
    renderApp(<ScorePage />)
    const cltvInput = screen.getByRole('spinbutton', { name: /customer lifetime value \(cltv\)/i })
    expect(cltvInput).toBeInTheDocument()
    expect(
      screen.getByText(/business valuation metric.*used for expected value.*does not affect churn prediction/i),
    ).toBeInTheDocument()
  })

  it('successful submit renders RiskBadge, LeverChips, and Recommendation with usd() and deltaWithRange()', async () => {
    const user = userEvent.setup()
    renderApp(<ScorePage />)

    const submitBtn = screen.getByRole('button', { name: /calculate score/i })
    await user.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText(/risk assessment/i)).toBeInTheDocument()
    })

    // Risk badge
    expect(screen.getByText(/critical/i)).toBeInTheDocument()
    expect(screen.getByText(/99.0%/)).toBeInTheDocument()

    // Levers
    const firstLever = scoreFixture.response_example.levers[0]
    expect(firstLever).toBeDefined()
    if (firstLever) {
      expect(screen.getByText(firstLever.label)).toBeInTheDocument()
    }

    // Recommendation with exact currency and delta format
    expect(screen.getByText(scoreFixture.response_example.recommendation.offer_name)).toBeInTheDocument()
    expect(screen.getByText('$705.82')).toBeInTheDocument()
    expect(screen.getByText('$120.51')).toBeInTheDocument()
    expect(screen.getByText('14% assumed (range 5%–24%)')).toBeInTheDocument()
  })

  it('passes axe accessibility checks on /score in both initial and submitted states', async () => {
    const user = userEvent.setup()
    const { container } = renderApp(<ScorePage />)

    // Initial state axe check
    const initialAxe = await axe(container)
    expect(initialAxe.violations).toEqual([])

    // Submit form
    const submitBtn = screen.getByRole('button', { name: /calculate score/i })
    await user.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText(/risk assessment/i)).toBeInTheDocument()
    })

    // Submitted state axe check
    const submittedAxe = await axe(container)
    expect(submittedAxe.violations).toEqual([])
  })

  describe('Rule C — Total Charges Auto-calculation & Manual Override', () => {
    it('Changing Monthly Charges or Tenure Months recomputes Total Charges to their product, rounded to 2 decimals', async () => {
      const user = userEvent.setup()
      renderApp(<ScorePage />)

      const tenureInput = screen.getByRole('spinbutton', { name: /^tenure months/i })
      const monthlyInput = screen.getByRole('spinbutton', { name: /^monthly charges/i })
      const totalInput = screen.getByRole('spinbutton', { name: /^total charges/i })

      await user.clear(tenureInput)
      await user.type(tenureInput, '12')

      await user.clear(monthlyInput)
      await user.type(monthlyInput, '75.50')

      // 12 * 75.50 = 906.00
      expect(totalInput).toHaveValue(906)
    })

    it('Manually editing Total Charges stops it from being overwritten by a subsequent Monthly Charges/Tenure Months change', async () => {
      const user = userEvent.setup()
      renderApp(<ScorePage />)

      const tenureInput = screen.getByRole('spinbutton', { name: /^tenure months/i })
      const monthlyInput = screen.getByRole('spinbutton', { name: /^monthly charges/i })
      const totalInput = screen.getByRole('spinbutton', { name: /^total charges/i })

      // Manual edit on Total Charges
      await user.clear(totalInput)
      await user.type(totalInput, '500')
      expect(totalInput).toHaveValue(500)

      // Subsequent change on Monthly Charges should NOT overwrite Total Charges
      await user.clear(monthlyInput)
      await user.type(monthlyInput, '100')

      expect(totalInput).toHaveValue(500)

      // Subsequent change on Tenure Months should NOT overwrite Total Charges
      await user.clear(tenureInput)
      await user.type(tenureInput, '10')

      expect(totalInput).toHaveValue(500)
    })

    it('"Reset to calculated value" recomputes and re-enables auto-calc', async () => {
      const user = userEvent.setup()
      renderApp(<ScorePage />)

      const tenureInput = screen.getByRole('spinbutton', { name: /^tenure months/i })
      const monthlyInput = screen.getByRole('spinbutton', { name: /^monthly charges/i })
      const totalInput = screen.getByRole('spinbutton', { name: /^total charges/i })

      await user.clear(tenureInput)
      await user.type(tenureInput, '5')

      await user.clear(monthlyInput)
      await user.type(monthlyInput, '80')

      // Manually edit Total Charges
      await user.clear(totalInput)
      await user.type(totalInput, '999')
      expect(totalInput).toHaveValue(999)

      // Reset button should now be visible
      const resetBtn = screen.getByRole('button', { name: /reset to calculated value/i })
      expect(resetBtn).toBeInTheDocument()

      await user.click(resetBtn)

      // Total Charges should recompute to 5 * 80 = 400
      expect(totalInput).toHaveValue(400)
      expect(screen.queryByRole('button', { name: /reset to calculated value/i })).not.toBeInTheDocument()

      // Subsequent change should now auto-calculate again
      await user.clear(monthlyInput)
      await user.type(monthlyInput, '90')
      // 5 * 90 = 450
      expect(totalInput).toHaveValue(450)
    })

    it('__totalChargesTouched is not present in the payload sent to POST /api/score', async () => {
      const user = userEvent.setup()
      let capturedPayload: Record<string, unknown> | null = null

      server.use(
        http.post('/api/score', async ({ request }) => {
          capturedPayload = (await request.json()) as Record<string, unknown>
          return HttpResponse.json(scoreFixture.response_example)
        }),
      )

      renderApp(<ScorePage />)
      const totalInput = screen.getByRole('spinbutton', { name: /^total charges/i })
      await user.clear(totalInput)
      await user.type(totalInput, '250')

      const submitBtn = screen.getByRole('button', { name: /calculate score/i })
      await user.click(submitBtn)

      await waitFor(() => expect(capturedPayload).not.toBeNull())
      expect(capturedPayload).not.toHaveProperty('__totalChargesTouched')
      expect(capturedPayload).toHaveProperty('Total Charges', 250)
    })
  })

  describe('Preview Note Generation', () => {
    it('generates an AI preview note when button clicked, with no Approve/Reject buttons', async () => {
      const user = userEvent.setup()
      renderApp(<ScorePage />)

      // Calculate score first
      const submitBtn = screen.getByRole('button', { name: /calculate score/i })
      await user.click(submitBtn)

      await waitFor(() => {
        expect(screen.getByText(/risk assessment/i)).toBeInTheDocument()
      })

      // Preview note card is visible
      expect(screen.getByText(/preview note/i)).toBeInTheDocument()
      expect(screen.getByText(/hypothetical profile — not a real customer, nothing is recorded/i)).toBeInTheDocument()

      // Click Generate note with AI
      const genBtn = screen.getByRole('button', { name: /generate note with ai/i })
      await user.click(genBtn)

      await waitFor(() => {
        expect(screen.getByText(/suggested talk track/i)).toBeInTheDocument()
      })

      // Verify no Approve or Reject buttons exist anywhere on the page
      expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
    })
  })
})
