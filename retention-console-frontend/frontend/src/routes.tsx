import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { QueuePage } from '@/features/queue/QueuePage'
import { CustomerPage } from '@/features/customer/CustomerPage'
import { NotFound } from '@/components/NotFound'
import { Skeleton } from '@/components/ui/Skeleton'

/**
 * Recharts is ~350 kB and only the dashboard needs it. Splitting it out keeps
 * the queue — the screen an agent opens 40 times a night — off that payload.
 */
const DashboardPage = lazy(() =>
  import('@/features/summary/DashboardPage').then((m) => ({ default: m.DashboardPage })),
)
const CatalogPage = lazy(() =>
  import('@/features/summary/CatalogPage').then((m) => ({ default: m.CatalogPage })),
)

const lazyRoute = (el: React.ReactNode) => (
  <Suspense fallback={<Skeleton className="h-96 w-full" />}>{el}</Suspense>
)

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <QueuePage /> },
      { path: 'customers/:id', element: <CustomerPage /> },
      { path: 'dashboard', element: lazyRoute(<DashboardPage />) },
      { path: 'catalog', element: lazyRoute(<CatalogPage />) },
      {
        path: '*',
        element: <NotFound />,
      },
    ],
  },
])
