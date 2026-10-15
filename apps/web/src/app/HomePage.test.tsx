import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT, PROJECT_ID, REVIEWER } from '@/test/fixtures';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const SECOND_PROJECT_ID = '019a3a5e-0000-7000-8000-000000000009';
const SUMMARY = {
  id: PROJECT.id,
  name: PROJECT.name,
  created_at: PROJECT.created_at,
  revision: PROJECT.revision,
  roles: PROJECT.roles,
  status: PROJECT.status,
};
const SECOND = {
  ...SUMMARY,
  id: SECOND_PROJECT_ID,
  name: 'Campus Parking Permits',
  roles: ['viewer' as const],
  status: {
    state: 'baseline' as const,
    baseline_version: 2,
    baseline_version_id: '019a3a5e-0000-7000-8000-0000000000e9',
    open_version_id: null,
  },
};

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    http.get('*/health/ready', () => HttpResponse.json({ status: 'ok' })),
    http.get('*/api/v1/projects/:projectId/sources', () =>
      HttpResponse.json({ source_versions: [] }),
    ),
    http.get('*/api/v1/projects/:projectId', () => HttpResponse.json(PROJECT)),
    http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)),
  );
});

describe('HomePage', () => {
  it("opens the chat of the reviewer's only project", async () => {
    server.use(http.get('*/api/v1/projects', () => HttpResponse.json({ projects: [SUMMARY] })));

    const router = renderApp('/');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/chat`);
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Chat' })).toBeInTheDocument();
  });

  it('lists the projects by name with their status and role when there are several', async () => {
    server.use(
      http.get('*/api/v1/projects', () => HttpResponse.json({ projects: [SUMMARY, SECOND] })),
    );

    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'Your projects' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: PROJECT.name })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/chat`,
    );
    expect(screen.getByRole('link', { name: SECOND.name })).toHaveAttribute(
      'href',
      `/projects/${SECOND_PROJECT_ID}/chat`,
    );
    expect(screen.getByText('Baseline v2 approved · Viewer')).toBeInTheDocument();
    expect(screen.queryByText(SECOND_PROJECT_ID)).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('offers a new project when the reviewer belongs to none', async () => {
    server.use(http.get('*/api/v1/projects', () => HttpResponse.json({ projects: [] })));

    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'No projects yet' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Project' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New project' })).toBeInTheDocument();
  });

  it('creates the first project and opens it when the user is done', async () => {
    let created = false;
    server.use(
      http.get('*/api/v1/projects', () =>
        HttpResponse.json({ projects: created ? [SUMMARY] : [] }),
      ),
      http.post('*/api/v1/projects', () => {
        created = true;
        return HttpResponse.json(PROJECT, { status: 201 });
      }),
    );
    const router = renderApp('/');

    await userEvent.click(await screen.findByRole('button', { name: 'New project' }));
    await userEvent.type(screen.getByRole('textbox', { name: 'Project name' }), PROJECT.name);
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }));

    // The list now holds one project, but the modal stays open on its second step.
    expect(await screen.findByLabelText('Step 2 of 2')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/');

    await userEvent.click(screen.getByRole('button', { name: 'Open project' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/chat`);
    });
  });

  it("shows the server's message and the API status when the projects cannot be loaded", async () => {
    server.use(
      http.get('*/api/v1/projects', () =>
        HttpResponse.json(errorBody('UNAVAILABLE', 'Try again shortly.', true), { status: 503 }),
      ),
    );

    renderApp('/');

    expect(
      await screen.findByText(/Could not load your projects\. Try again shortly\./),
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
