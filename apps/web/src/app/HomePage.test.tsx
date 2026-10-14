import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { errorBody, PROJECT, PROJECT_ID, REVIEWER } from '@/test/fixtures';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const SECOND_PROJECT_ID = '019a3a5e-0000-7000-8000-000000000009';

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    http.get('*/health/ready', () => HttpResponse.json({ status: 'ok' })),
    http.get('*/api/v1/projects/:projectId/sources', () =>
      HttpResponse.json({ source_versions: [] }),
    ),
    http.get('*/api/v1/projects/:projectId', () => HttpResponse.json(PROJECT)),
  );
});

describe('HomePage', () => {
  it("opens the chat of the reviewer's only project", async () => {
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json({
          ...REVIEWER,
          memberships: [
            { project_id: PROJECT_ID, role: 'editor' },
            { project_id: PROJECT_ID, role: 'approver' },
          ],
        }),
      ),
    );

    const router = renderApp('/');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/chat`);
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Chat' })).toBeInTheDocument();
  });

  it('lists the projects by id when the reviewer belongs to several', async () => {
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json({
          ...REVIEWER,
          memberships: [
            { project_id: PROJECT_ID, role: 'editor' },
            { project_id: SECOND_PROJECT_ID, role: 'viewer' },
          ],
        }),
      ),
    );

    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'Your projects' })).toBeInTheDocument();
    expect(screen.getByText(SECOND_PROJECT_ID)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: `Backlog of project ${PROJECT_ID}` })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog`,
    );
    expect(
      screen.getByRole('link', { name: `Sources of project ${SECOND_PROJECT_ID}` }),
    ).toHaveAttribute('href', `/projects/${SECOND_PROJECT_ID}/sources`);
  });

  it('says so when the reviewer belongs to no project', async () => {
    server.use(http.get('*/api/v1/me', () => HttpResponse.json({ ...REVIEWER, memberships: [] })));

    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'No projects yet' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Project' })).not.toBeInTheDocument();
  });

  it("shows the server's message and the API status when the account cannot be loaded", async () => {
    server.use(
      http.get('*/api/v1/me', () =>
        HttpResponse.json(errorBody('UNAUTHENTICATED', 'Sign in to continue.'), { status: 401 }),
      ),
    );

    renderApp('/');

    expect(
      await screen.findByText(/Could not load your projects\. Sign in to continue\./),
    ).toBeInTheDocument();
    expect(await screen.findByText('API ready')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Try again' }).length).toBeGreaterThan(0);
  });

  it('explains an address that matches no page', async () => {
    server.use(http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)));

    renderApp('/nowhere');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Page not found' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to your projects' })).toHaveAttribute('href', '/');
  });
});
