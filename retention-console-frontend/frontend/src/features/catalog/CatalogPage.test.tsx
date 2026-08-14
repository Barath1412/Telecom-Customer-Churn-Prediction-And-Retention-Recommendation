import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { axe } from 'vitest-axe'
import { CatalogPage } from './CatalogPage'
import { server } from '@/mocks/server'
import { renderApp, screen, waitFor } from '@/test/utils'

describe('CatalogPage', () => {
  it('renders loading skeleton with accessible name', () => {
    renderApp(<CatalogPage />)
    expect(screen.getByRole('status', { name: /loading catalog/i })).toBeInTheDocument()
  })

  it('renders all six offers from fixture', async () => {
    renderApp(<CatalogPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /offer catalog/i })).toBeInTheDocument(),
    )

    expect(screen.getByText('1-year contract at 10% off')).toBeInTheDocument()
    expect(screen.getByText('2-year contract at 15% off')).toBeInTheDocument()
    expect(screen.getByText('Tech Support bundled free for 12 months')).toBeInTheDocument()
    expect(screen.getByText('Online Security bundled free for 12 months')).toBeInTheDocument()
    expect(
      screen.getByText('Tech Support + Online Security bundle, 12 months'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Switch to autopay, $5/month credit for 12 months'),
    ).toBeInTheDocument()
  })

  it('renders all six offer_id strings verbatim without modification', async () => {
    renderApp(<CatalogPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /offer catalog/i })).toBeInTheDocument(),
    )

    // Dedicated assertion verifying exact byte-for-byte audit log identifiers
    const expectedIds = [
      'OFF-CONTRACT-1Y',
      'OFF-CONTRACT-2Y',
      'OFF-TECHSUP-12',
      'OFF-SEC-12',
      'OFF-BUNDLE-ALL',
      'OFF-AUTOPAY',
    ]

    expectedIds.forEach((id) => {
      expect(screen.getByText(id)).toBeInTheDocument()
    })
  })

  it('formats every assumed effect via deltaWithRange uncertainty string', async () => {
    renderApp(<CatalogPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /offer catalog/i })).toBeInTheDocument(),
    )

    // Asserts that delta figures contain the assumed point estimate and confidence interval
    expect(screen.getByText('12% assumed (range 4%–20%)')).toBeInTheDocument()
    expect(screen.getByText('18% assumed (range 6%–28%)')).toBeInTheDocument()
    expect(screen.getByText('8% assumed (range 2%–15%)')).toBeInTheDocument()
    expect(screen.getByText('5% assumed (range 1%–11%)')).toBeInTheDocument()
    expect(screen.getByText('14% assumed (range 5%–24%)')).toBeInTheDocument()
    expect(screen.getByText('4% assumed (range 0%–10%)')).toBeInTheDocument()
  })

  it('renders policy thresholds correctly', async () => {
    renderApp(<CatalogPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /policy thresholds/i })).toBeInTheDocument(),
    )

    expect(screen.getByText('Margin floor')).toBeInTheDocument()
    expect(screen.getByText('18%')).toBeInTheDocument()

    expect(screen.getByText('Max discount')).toBeInTheDocument()
    expect(screen.getByText('20%')).toBeInTheDocument()

    expect(screen.getByText('90 days')).toBeInTheDocument()
    expect(screen.getByText('$150.00')).toBeInTheDocument()
  })

  it('shows an actionable error instead of a blank catalog on failure', async () => {
    server.use(http.get('/api/catalog', () => new HttpResponse(null, { status: 500 })))
    renderApp(<CatalogPage />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('passes axe accessibility checks on /catalog with zero violations', async () => {
    const { container } = renderApp(<CatalogPage />)
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: /offer catalog/i })).toBeInTheDocument(),
    )
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })
})
