import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { HealthStatus } from '@/features/health';
import { server } from '@/test/server';

function renderWithQueryClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <HealthStatus />
    </QueryClientProvider>,
  );
}

describe('HealthStatus', () => {
  it('reports the API as ready when the health check succeeds', async () => {
    server.use(http.get('*/health/ready', () => HttpResponse.json({ status: 'ok' })));

    renderWithQueryClient();

    expect(await screen.findByText('API ready')).toBeInTheDocument();
  });

  it('reports the API as unavailable when the health check fails', async () => {
    server.use(
      http.get('*/health/ready', () =>
        HttpResponse.json(
          {
            code: 'DATABASE_UNAVAILABLE',
            message: 'The database is unreachable',
            request_id: '019a3a5e-1111-7000-8000-000000000000',
            retryable: true,
            details: {},
          },
          { status: 503 },
        ),
      ),
    );

    renderWithQueryClient();

    expect(await screen.findByText('API unavailable')).toBeInTheDocument();
  });
});
