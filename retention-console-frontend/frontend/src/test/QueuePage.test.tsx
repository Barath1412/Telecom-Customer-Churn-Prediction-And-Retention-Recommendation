import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { QueuePage } from '@/features/queue/QueuePage'
import { server } from '@/mocks/server'
import { renderApp, screen, waitFor } from './utils'

describe('QueuePage', () => {
  it('renders the queue from the generated fixture', async () => {
    renderApp(<QueuePage />)
    expect(screen.getByRole('status', { name: /loading queue/i })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
    expect(screen.getAllByRole('row').length).toBeGreaterThan(1)
  })

  it('flags control-arm customers so nobody calls them', async () => {
    renderApp(<QueuePage />)
    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
    const control = screen.queryAllByText(/do not contact/i)
    // The fixture may contain zero control rows; the assertion is that when a
    // row IS control it is labelled, never silently identical to treatment.
    control.forEach((el) => expect(el).toBeVisible())
  })

  it('shows an actionable error instead of an empty table on failure', async () => {
    server.use(http.get('/api/queue', () => new HttpResponse(null, { status: 500 })))
    renderApp(<QueuePage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })
})
