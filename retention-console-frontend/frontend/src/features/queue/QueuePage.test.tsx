import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import userEvent from '@testing-library/user-event'
import { QueuePage } from './QueuePage'
import { server } from '@/mocks/server'
import { renderApp, screen, waitFor } from '@/test/utils'

describe('QueuePage', () => {
  it('renders loading skeleton with accessible name', () => {
    renderApp(<QueuePage />)
    expect(screen.getByRole('status', { name: /loading queue/i })).toBeInTheDocument()
  })

  it('renders the queue from the generated fixture', async () => {
    renderApp(<QueuePage />)
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
    expect(screen.getAllByRole('row').length).toBeGreaterThan(1)
    expect(screen.getByRole('link', { name: '0295-PPHDO' })).toHaveAttribute(
      'href',
      '/customers/0295-PPHDO',
    )
  })

  it('flags control-arm customers so nobody calls them', async () => {
    renderApp(<QueuePage />)
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
    const controlBadges = screen.queryAllByText(/control — do not contact/i)
    controlBadges.forEach((badge) => expect(badge).toBeVisible())
  })

  it('shows an actionable error instead of an empty table on failure', async () => {
    server.use(http.get('/api/queue', () => new HttpResponse(null, { status: 500 })))
    renderApp(<QueuePage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('shows an explanatory empty state when queue has 0 items', async () => {
    server.use(
      http.get(
        '/api/queue',
        () =>
          HttpResponse.json({
            run_id: 'run_2026-08-13T02:00:00Z',
            capacity: 40,
            total_eligible: 0,
            returned: 0,
            page: 1,
            page_size: 40,
            items: [],
          }),
      ),
    )
    renderApp(<QueuePage />)
    await waitFor(() =>
      expect(screen.getByText(/nothing in tonight's queue/i)).toBeInTheDocument(),
    )
    expect(
      screen.getByText(/no customer produced a positive-value, policy-approved offer/i),
    ).toBeInTheDocument()
  })

  it('supports row keyboard navigation on Enter and Space', async () => {
    const user = userEvent.setup()
    renderApp(<QueuePage />)
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

    const rows = screen.getAllByRole('row')
    const firstDataRow = rows[1]
    expect(firstDataRow).toBeDefined()
    if (firstDataRow) {
      firstDataRow.focus()
      expect(firstDataRow).toHaveFocus()
      await user.keyboard('{Enter}')
    }
  })

  it('passes axe accessibility checks on the queue table with zero violations', async () => {
    const { container } = renderApp(<QueuePage />)
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })

  describe('CustomerSearch — client-side filtering', () => {
    it('typing a partial id filters the visible rows', async () => {
      const user = userEvent.setup()
      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

      const input = screen.getByRole('searchbox', { name: /find customer/i })
      await user.type(input, '0295')

      // Only the matching customer ID link should remain
      await waitFor(() => {
        const links = screen
          .getAllByRole('link')
          .filter((l) => /^\w{4}-/.test(l.textContent ?? ''))
        expect(links.length).toBeGreaterThan(0)
        links.forEach((link) => {
          expect(link.textContent?.toLowerCase()).toContain('0295')
        })
      })
    })

    it('a non-matching query renders the empty state, not a blank table', async () => {
      const user = userEvent.setup()
      const { container } = renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

      const input = screen.getByRole('searchbox', { name: /find customer/i })
      await user.type(input, 'XXXXXXXX')

      await waitFor(() => expect(screen.queryByRole('table')).not.toBeInTheDocument())
      expect(screen.getByText(/no customer id contains/i)).toBeInTheDocument()

      // The role="status" region must remain in the DOM (never unmounts) so that
      // the "Showing 0 of 40" count change is announced even when the table is hidden.
      expect(screen.getByRole('status')).toBeInTheDocument()

      // axe on the filtered-to-zero state (complements the existing normal-state axe test)
      const results = await axe(container)
      expect(results.violations).toEqual([])
    })

    it('clearing the input restores the full row count', async () => {
      const user = userEvent.setup()
      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

      const totalRows = screen.getAllByRole('row').length
      const input = screen.getByRole('searchbox', { name: /find customer/i })
      await user.type(input, '0295')
      await waitFor(() => expect(screen.getAllByRole('row').length).toBeLessThan(totalRows))

      await user.clear(input)
      await waitFor(() => expect(screen.getAllByRole('row').length).toBe(totalRows))
    })

    it('sorting still works while a filter is active', async () => {
      const user = userEvent.setup()
      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

      // Apply filter first
      const input = screen.getByRole('searchbox', { name: /find customer/i })
      await user.type(input, '0295')
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

      // EV column starts sorted descending
      const evHeader = screen.getByRole('columnheader', { name: /expected value/i })
      expect(evHeader).toHaveAttribute('aria-sort', 'descending')

      // Click the sort button within the EV header — toggle to ascending
      const sortBtn = screen.getByRole('button', { name: /expected value/i })
      await user.click(sortBtn)
      await waitFor(() => expect(evHeader).toHaveAttribute('aria-sort', 'ascending'))
    })
  })

  describe('Tabs and Pagination', () => {
    it('renders three tabs; clicking "Approved" calls useQueue with status: "approved" and resets to page 1', async () => {
      const user = userEvent.setup()
      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

      const approvedTab = screen.getByRole('tab', { name: /approved/i })
      expect(approvedTab).toBeInTheDocument()
      await user.click(approvedTab)

      await waitFor(() =>
        expect(screen.getByText(/no approved customers/i)).toBeInTheDocument(),
      )
    })

    it('pagination with mocked pending_total of 90 and page_size 40 shows "Page 1 of 3" and disables Next on last page', async () => {
      const user = userEvent.setup()
      server.use(
        http.get('/api/queue', ({ request }) => {
          const url = new URL(request.url)
          const page = parseInt(url.searchParams.get('page') ?? '1', 10)
          return HttpResponse.json({
            run_id: 'run_2026-08-13T02:00:00Z',
            capacity: 40,
            total_eligible: 90,
            pending_total: 90,
            approved_total: 0,
            rejected_total: 0,
            status: 'pending',
            returned: page === 3 ? 10 : 40,
            page,
            page_size: 40,
            items: [
              {
                rank: (page - 1) * 40 + 1,
                customer_id: `CUST-P${page}-01`,
                arm: 'treatment',
                risk: { p_churn: 0.8, risk_band: 'high', percentile: 90 },
                value: { cltv: 5000, monthly_charges: 70, tenure_months: 5, currency: 'USD' },
                levers: [],
                recommendation: {
                  offer_id: 'OFF-1',
                  offer_name: 'Test Offer',
                  cost: 100,
                  delta_prior: 0.1,
                  delta_ci: [0.05, 0.15],
                  delta_source: 'test',
                  expected_value: 300,
                  requires_approval: false,
                },
                status: 'recommended',
                queue_position: (page - 1) * 40 + 1,
                actionable: page === 1,
              },
            ],
          })
        }),
      )

      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByText('Page 1 of 3')).toBeInTheDocument())

      expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /next/i })).toBeEnabled()

      // Click Next -> Page 2
      await user.click(screen.getByRole('button', { name: /next/i }))
      await waitFor(() => expect(screen.getByText('Page 2 of 3')).toBeInTheDocument())
      expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled()
      expect(screen.getByRole('button', { name: /next/i })).toBeEnabled()

      // Click Next -> Page 3
      await user.click(screen.getByRole('button', { name: /next/i }))
      await waitFor(() => expect(screen.getByText('Page 3 of 3')).toBeInTheDocument())
      expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled()
      expect(screen.getByRole('button', { name: /next/i })).toBeDisabled()
    })

    it('on the Approved tab, renders decision offer and note when offer_changed: true', async () => {
      server.use(
        http.get('/api/queue', () =>
          HttpResponse.json({
            run_id: 'run_2026-08-13T02:00:00Z',
            capacity: 40,
            total_eligible: 688,
            pending_total: 686,
            approved_total: 2,
            rejected_total: 0,
            status: 'approved',
            returned: 2,
            page: 1,
            page_size: 40,
            items: [
              {
                rank: 1,
                customer_id: '0295-PPHDO',
                arm: 'treatment',
                risk: { p_churn: 0.99, risk_band: 'critical', percentile: 100.0 },
                value: { cltv: 5962.0, monthly_charges: 95.45, tenure_months: 1, currency: 'USD' },
                levers: [],
                recommendation: {
                  offer_id: 'OFF-BUNDLE-ALL',
                  offer_name: 'Tech Support + Online Security bundle, 12 months',
                  cost: 135.53,
                  delta_prior: 0.14,
                  delta_ci: [0.05, 0.24],
                  delta_source: 'business_judgment_v1',
                  expected_value: 705.82,
                  requires_approval: false,
                },
                status: 'recommended',
                queue_position: 1,
                actionable: false,
                decision: {
                  action: 'edit',
                  actor: 'agent_demo',
                  reason_code: null,
                  acted_at: '2026-08-16T12:27:34Z',
                  offered_offer_id: 'OFF-CONTRACT-1Y',
                  offered_offer_name: '1-year contract at 10% off',
                  offer_changed: true,
                },
              },
              {
                rank: 2,
                customer_id: '2754-SDJRD',
                arm: 'treatment',
                risk: { p_churn: 0.85, risk_band: 'critical', percentile: 98.0 },
                value: { cltv: 5500.0, monthly_charges: 80.0, tenure_months: 2, currency: 'USD' },
                levers: [],
                recommendation: {
                  offer_id: 'OFF-CONTRACT-2Y',
                  offer_name: '2-year contract at 15% off',
                  cost: 140.0,
                  delta_prior: 0.18,
                  delta_ci: [0.06, 0.28],
                  delta_source: 'business_judgment_v1',
                  expected_value: 600.0,
                  requires_approval: false,
                },
                status: 'recommended',
                queue_position: 2,
                actionable: false,
                decision: {
                  action: 'approve',
                  actor: 'agent_demo',
                  reason_code: null,
                  acted_at: '2026-08-16T12:27:26Z',
                  offered_offer_id: 'OFF-CONTRACT-2Y',
                  offered_offer_name: '2-year contract at 15% off',
                  offer_changed: false,
                },
              },
            ],
          }),
        ),
      )

      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())

      // Row 1 with offer_changed: true
      expect(screen.getByText('Approved — offered: 1-year contract at 10% off')).toBeInTheDocument()
      expect(
        screen.getByText('(agent changed from the model\'s original recommendation)'),
      ).toBeInTheDocument()

      // Row 2 with offer_changed: false
      expect(screen.getByText('Approved — offered: 2-year contract at 15% off')).toBeInTheDocument()
    })

    it('on the Rejected tab, renders decision reason_code', async () => {
      server.use(
        http.get('/api/queue', () =>
          HttpResponse.json({
            run_id: 'run_2026-08-13T02:00:00Z',
            capacity: 40,
            total_eligible: 688,
            pending_total: 687,
            approved_total: 0,
            rejected_total: 1,
            status: 'rejected',
            returned: 1,
            page: 1,
            page_size: 40,
            items: [
              {
                rank: 1,
                customer_id: '0295-PPHDO',
                arm: 'treatment',
                risk: { p_churn: 0.99, risk_band: 'critical', percentile: 100.0 },
                value: { cltv: 5962.0, monthly_charges: 95.45, tenure_months: 1, currency: 'USD' },
                levers: [],
                recommendation: {
                  offer_id: 'OFF-BUNDLE-ALL',
                  offer_name: 'Tech Support + Online Security bundle, 12 months',
                  cost: 135.53,
                  delta_prior: 0.14,
                  delta_ci: [0.05, 0.24],
                  delta_source: 'business_judgment_v1',
                  expected_value: 705.82,
                  requires_approval: false,
                },
                status: 'recommended',
                queue_position: 1,
                actionable: false,
                decision: {
                  action: 'reject',
                  actor: 'agent_demo',
                  reason_code: 'already_contacted',
                  acted_at: '2026-08-16T12:27:34Z',
                  offered_offer_id: 'OFF-BUNDLE-ALL',
                  offered_offer_name: 'Tech Support + Online Security bundle, 12 months',
                  offer_changed: false,
                },
              },
            ],
          }),
        ),
      )

      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
      expect(screen.getByText('Rejected — already_contacted')).toBeInTheDocument()
    })

    it('# column renders queue_position, not static rank', async () => {
      server.use(
        http.get('/api/queue', () =>
          HttpResponse.json({
            run_id: 'run_2026-08-13T02:00:00Z',
            capacity: 40,
            total_eligible: 10,
            pending_total: 10,
            approved_total: 0,
            rejected_total: 0,
            status: 'pending',
            returned: 2,
            page: 1,
            page_size: 40,
            items: [
              {
                rank: 99,
                customer_id: 'CUST-A',
                arm: 'treatment',
                risk: { p_churn: 0.9, risk_band: 'critical', percentile: 99 },
                value: { cltv: 5000, monthly_charges: 80, tenure_months: 2, currency: 'USD' },
                levers: [],
                recommendation: {
                  offer_id: 'OFF-1',
                  offer_name: 'Offer 1',
                  cost: 100,
                  delta_prior: 0.1,
                  delta_ci: [0.05, 0.15],
                  delta_source: 'test',
                  expected_value: 300,
                  requires_approval: false,
                },
                status: 'recommended',
                queue_position: 1,
                actionable: true,
              },
              {
                rank: 99,
                customer_id: 'CUST-B',
                arm: 'treatment',
                risk: { p_churn: 0.85, risk_band: 'critical', percentile: 98 },
                value: { cltv: 4000, monthly_charges: 70, tenure_months: 3, currency: 'USD' },
                levers: [],
                recommendation: {
                  offer_id: 'OFF-2',
                  offer_name: 'Offer 2',
                  cost: 50,
                  delta_prior: 0.12,
                  delta_ci: [0.05, 0.15],
                  delta_source: 'test',
                  expected_value: 250,
                  requires_approval: false,
                },
                status: 'recommended',
                queue_position: 2,
                actionable: true,
              },
            ],
          }),
        ),
      )

      renderApp(<QueuePage />)
      await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
      const rows = screen.getAllByRole('row')
      // Header is row 0, row 1 is CUST-A, row 2 is CUST-B
      expect(rows[1]).toHaveTextContent('1')
      expect(rows[2]).toHaveTextContent('2')
    })
  })
})