import { beforeAll, describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import { DashboardPage } from './DashboardPage'
import { server } from '@/mocks/server'
import { renderApp, screen, waitFor, within } from '@/test/utils'

beforeAll(() => {
  if (typeof globalThis.ResizeObserver === 'undefined') {
    globalThis.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver
  }
})

describe('DashboardPage', () => {
  it('renders loading skeleton with accessible name', () => {
    renderApp(<DashboardPage />)
    expect(screen.getByRole('status', { name: /loading dashboard/i })).toBeInTheDocument()
  })

  it('renders dashboard KPI tiles from fixture', async () => {
    renderApp(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /decision funnel/i })).toBeInTheDocument(),
    )

    expect(screen.getByText(/precision at capacity/i)).toBeInTheDocument()
    expect(screen.getByText(/offer spend/i)).toBeInTheDocument()
    expect(screen.getByText(/expected value/i)).toBeInTheDocument()
    expect(screen.getByText(/held back \(control\)/i)).toBeInTheDocument()
  })

  it('renders expected-value tile with mandatory assumption caveat', async () => {
    renderApp(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /decision funnel/i })).toBeInTheDocument(),
    )
    expect(screen.getByText('assumption-based — not measured')).toBeInTheDocument()
  })

  it('renders equivalent accessible data table for the decision funnel', async () => {
    renderApp(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /decision funnel/i })).toBeInTheDocument(),
    )

    const funnelTable = screen.getByRole('table', { name: /decision funnel counts/i })
    expect(funnelTable).toBeInTheDocument()

    // Assert that every funnel stage and count from fixture is present in the table
    const tableScope = within(funnelTable)
    expect(tableScope.getByRole('rowheader', { name: 'Scored' })).toBeInTheDocument()
    expect(tableScope.getByText('1,409')).toBeInTheDocument()

    expect(tableScope.getByRole('rowheader', { name: 'Involuntary' })).toBeInTheDocument()
    expect(tableScope.getByText('9')).toBeInTheDocument()

    expect(tableScope.getByRole('rowheader', { name: 'No offer' })).toBeInTheDocument()
    expect(tableScope.getByText('657')).toBeInTheDocument()

    expect(tableScope.getByRole('rowheader', { name: 'Recommended' })).toBeInTheDocument()
    expect(tableScope.getByText('743')).toBeInTheDocument()

    expect(tableScope.getByRole('rowheader', { name: 'Queued' })).toBeInTheDocument()
    expect(tableScope.getByText('40')).toBeInTheDocument()
  })

  it('renders allocation parity table with demographic groups', async () => {
    renderApp(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /allocation parity/i })).toBeInTheDocument(),
    )

    const parityTable = screen.getByRole('table', {
      name: /allocation parity across demographic groups/i,
    })
    expect(parityTable).toBeInTheDocument()

    const tableScope = within(parityTable)
    expect(tableScope.getByText('Female')).toBeInTheDocument()
    expect(tableScope.getByText('Male')).toBeInTheDocument()
    expect(tableScope.getAllByText('Senior Citizen')).toHaveLength(2)
  })

  it('shows an actionable error instead of a blank dashboard on failure', async () => {
    server.use(http.get('/api/summary', () => new HttpResponse(null, { status: 500 })))
    renderApp(<DashboardPage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('passes axe accessibility checks on /dashboard with zero violations', async () => {
    const { container } = renderApp(<DashboardPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /decision funnel/i })).toBeInTheDocument(),
    )
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })
})
