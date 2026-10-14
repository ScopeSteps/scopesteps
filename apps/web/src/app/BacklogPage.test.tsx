import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { BacklogPage } from '@/app/BacklogPage';
import {
  BACKLOG,
  BRIEF,
  makeRun,
  PROJECT_ID,
  REVIEWER,
  RUN_ID,
  TRANSCRIPT,
  VERSION_ID,
} from '@/test/fixtures';
import { server } from '@/test/server';

function renderPage(search: string) {
  const router = createMemoryRouter(
    [{ path: '/projects/:projectId/backlog', element: <BacklogPage /> }],
    { initialEntries: [`/projects/${PROJECT_ID}/backlog${search}`] },
  );
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)),
    http.get(`*/api/v1/projects/${PROJECT_ID}/sources`, () =>
      HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] }),
    ),
    http.get(`*/api/v1/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
      HttpResponse.json(BACKLOG),
    ),
    http.get(`*/api/v1/runs/${RUN_ID}`, () =>
      HttpResponse.json(
        makeRun({ status: 'ready_for_review', revision: 9, candidate_version_id: VERSION_ID }),
      ),
    ),
  );
});

describe('BacklogPage', () => {
  it('offers to generate a backlog when the URL names no run or version', async () => {
    renderPage('');

    expect(await screen.findByRole('button', { name: 'Generate backlog' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Agent run' })).not.toBeInTheDocument();
  });

  it('restores a finished run and its saved candidate from the run id in the URL', async () => {
    renderPage(`?run=${RUN_ID}`);

    expect(await screen.findByText('Ready for review')).toBeInTheDocument();
    expect(
      await screen.findByRole('article', { name: 'Story Search for and book a one-off slot' }),
    ).toBeInTheDocument();
    expect(screen.getByText(`Version ${VERSION_ID}`)).toBeInTheDocument();
  });

  it('shows a backlog version by its id alone', async () => {
    renderPage(`?version=${VERSION_ID}`);

    expect(await screen.findByText('Draft: not approved')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Agent run' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Generate backlog' })).not.toBeInTheDocument();
  });
});
