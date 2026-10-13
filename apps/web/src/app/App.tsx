import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';
import { PreferencesProvider } from '@/app/shell/PreferencesProvider';
import { ToastProvider } from '@/components/ToastProvider';
import { shouldRetry } from '@/lib/apiError';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: shouldRetry } } });

const router = createBrowserRouter(routes);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PreferencesProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </PreferencesProvider>
    </QueryClientProvider>
  );
}
