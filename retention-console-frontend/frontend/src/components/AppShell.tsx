import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { cn } from '@/lib/cn'

const NAV = [
  { to: '/', label: 'Queue', end: true },
  { to: '/dashboard', label: 'Run summary', end: false },
  { to: '/catalog', label: 'Offer catalog', end: false },
  { to: '/score', label: 'Manual scoring', end: false },
  { to: '/llm-analytics', label: 'LLM Analytics', end: false },
]

export function AppShell() {
  const { pathname } = useLocation()

  useEffect(() => {
    document.getElementById('main')?.focus()
  }, [pathname])

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* First tabbable element on every page. */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-ink focus:px-3 focus:py-2 focus:text-surface"
      >
        Skip to main content
      </a>

      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-4">
          <span className="text-sm font-semibold tracking-tight">Retention Console</span>
          <nav aria-label="Primary" className="flex gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  cn(
                    'rounded px-3 py-1.5 text-sm',
                    isActive ? 'bg-raised font-medium text-ink' : 'text-ink-2 hover:bg-raised',
                  )
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto max-w-[1400px] px-4 py-6 outline-none">
        <Outlet />
      </main>
    </div>
  )
}
