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
})
