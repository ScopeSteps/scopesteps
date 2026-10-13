import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';

import { routes } from '@/app/routes';
import { PreferencesProvider } from '@/app/shell/PreferencesProvider';
import { ToastProvider } from '@/components/ToastProvider';

/** Renders the whole app, shell included, at a path. Returns the router to read the location. */
export function renderApp(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <PreferencesProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </PreferencesProvider>
    </QueryClientProvider>,
  );
  return router;
}
