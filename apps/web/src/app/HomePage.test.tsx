import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';

import { HomePage } from '@/app/HomePage';
import { server } from '@/test/server';

const PROJECT_ID = '019a3a5e-0000-7000-8000-000000000001';

describe('HomePage', () => {
  it("links to the sources and the backlog of the reviewer's project", async () => {
    server.use(
      http.get('*/health/ready', () => HttpResponse.json({ status: 'ok' })),
      http.get('*/api/v1/me', () =>
        HttpResponse.json({
          id: '019a3a5e-0000-7000-8000-000000000002',
          email: 'reviewer@scopesteps.local',
          display_name: 'Local Reviewer',
          memberships: [
            { project_id: PROJECT_ID, role: 'editor' },
            { project_id: PROJECT_ID, role: 'approver' },
          ],
        }),
      ),
    );

    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <HomePage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const links = await screen.findAllByRole('link', { name: 'Sources' });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', `/projects/${PROJECT_ID}/sources`);
    expect(screen.getByRole('link', { name: 'Backlog' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog`,
    );
  });
});
