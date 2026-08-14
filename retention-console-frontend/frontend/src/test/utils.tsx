import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactElement, ReactNode } from 'react'
import { NotifierProvider } from '@/components/ui/Notifier'

function Providers({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <NotifierProvider>
        <MemoryRouter>{children}</MemoryRouter>
      </NotifierProvider>
    </QueryClientProvider>
  )
}

export const renderApp = (ui: ReactElement, options?: RenderOptions) =>
  render(ui, { wrapper: Providers, ...options })

export * from '@testing-library/react'
