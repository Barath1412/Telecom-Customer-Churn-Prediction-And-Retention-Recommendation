import { QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { queryClient } from '@/lib/queryClient'
import { NotifierProvider } from '@/components/ui/Notifier'
import { router } from '@/routes'

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <NotifierProvider>
        <RouterProvider router={router} />
      </NotifierProvider>
    </QueryClientProvider>
  )
}



