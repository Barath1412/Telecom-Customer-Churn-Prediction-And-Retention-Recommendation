import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'
import { renderApp, screen } from './utils'
import { AppShell } from '@/components/AppShell'

describe('AppShell Accessibility & Routing', () => {
  it('has zero axe violations on an empty route', async () => {
    const { container } = renderApp(<AppShell />)
    const results = await axe(container)
    expect(results.violations).toEqual([])
  })

  it('renders skip link as first tabbable element', () => {
    renderApp(<AppShell />)
    const skipLink = screen.getByText('Skip to main content')
    expect(skipLink).toBeInTheDocument()
    expect(skipLink).toHaveAttribute('href', '#main')
  })

  it('includes primary navigation with correct accessible label', () => {
    renderApp(<AppShell />)
    expect(screen.getByRole('navigation', { name: /primary/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /queue/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /run summary/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /offer catalog/i })).toBeInTheDocument()
  })

  it('renders main landmark with tabIndex for focus management', () => {
    renderApp(<AppShell />)
    const main = screen.getByRole('main')
    expect(main).toHaveAttribute('id', 'main')
    expect(main).toHaveAttribute('tabindex', '-1')
  })
})
