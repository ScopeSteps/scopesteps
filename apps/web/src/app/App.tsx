import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router';

import { HomePage } from '@/app/HomePage';
import { SourcesPage } from '@/app/SourcesPage';
import { shouldRetry } from '@/lib/apiError';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: shouldRetry } } });

const router = createBrowserRouter([
  { path: '/', element: <HomePage /> },
  { path: '/projects/:projectId/sources', element: <SourcesPage /> },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
