import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT, PROJECT_ID, REVIEWER } from '@/test/fixtures';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { resetViewport, setNarrowViewport } from '@/test/viewport';

type Schemas = components['schemas'];
type ProjectWork = Schemas['ProjectWorkResponse'];
type MyWork = Schemas['MyWorkResponse'];

const LIBRARY_ID = '019a3a5e-0000-7000-8000-000000000011';
const LAB_ID = '019a3a5e-0000-7000-8000-000000000012';
const HALL_ID = '019a3a5e-0000-7000-8000-000000000013';
const NO_BASELINE = PROJECT.status;
const DRAFT = {
  state: 'draft_in_progress' as const,
  baseline_version: null,
  baseline_version_id: null,
  open_version_id: '019a3a5e-0000-7000-8000-0000000000e1',
};
const ACTIVITY = { events: 4, latest_at: '2026-10-28T09:00:00Z' };

function project(overrides: Partial<ProjectWork> & Pick<ProjectWork, 'id' | 'name'>): ProjectWork {
  return {
    roles: ['viewer'],
    status: NO_BASELINE,
    waiting: 0,
    approver: null,
    editor: null,
    recent_activity: null,
    ...overrides,
  };
}

/** Approver on Library App, editor on Lab Bookings, viewer on Sports Hall. */
const APPROVING = project({
  id: LIBRARY_ID,
  name: 'Library App',
  roles: ['approver'],
  status: DRAFT,
  waiting: 3,
  approver: { change_requests_in_review: 2, draft_ready_for_approval: true },
  recent_activity: ACTIVITY,
});
const EDITING = project({
  id: LAB_ID,
  name: 'Lab Bookings',
  roles: ['editor'],
  waiting: 6,
  editor: { open_questions: 1, draft_blockers: 3, unconfirmed_speakers: 2 },
  recent_activity: ACTIVITY,
});
const VIEWING = project({
  id: HALL_ID,
  name: 'Sports Hall',
  roles: ['viewer'],
  recent_activity: { events: 1, latest_at: '2026-10-27T09:00:00Z' },
});

function myWork(projects: ProjectWork[], roles?: MyWork['roles']): MyWork {
  return {
    projects,
    roles: roles ?? [
      { role: 'approver', projects: 1, waiting: 3 },
      { role: 'editor', projects: 1, waiting: 6 },
      { role: 'viewer', projects: 1, waiting: 0 },
    ],
    activity_window_days: 7,
  };
}

function serveMyWork(work: MyWork) {
  server.use(http.get('*/api/v1/me/work', () => HttpResponse.json(work)));
}

function projectNames(): string[] {
  const list = screen.getByRole('region', { name: 'My projects' });
  return within(list)
    .getAllByRole('link')
    .map((link) => link.textContent);
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    http.get('*/health/ready', () => HttpResponse.json({ status: 'ok' })),
    http.get('*/api/v1/projects', () => HttpResponse.json({ projects: [] })),
    http.get('*/api/v1/projects/:projectId/sources', () =>
      HttpResponse.json({ source_versions: [] }),
    ),
    http.get('*/api/v1/projects/:projectId', () => HttpResponse.json(PROJECT)),
    http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)),
  );
});

afterEach(() => {
  resetViewport();
});

describe('HomePage', () => {
  it('stays on the home page with a single project instead of opening it', async () => {
    serveMyWork(
      myWork(
        [project({ id: PROJECT_ID, name: PROJECT.name, roles: ['editor'], editor: null })],
        [
          { role: 'approver', projects: 0, waiting: 0 },
          { role: 'editor', projects: 1, waiting: 0 },
          { role: 'viewer', projects: 0, waiting: 0 },
        ],
      ),
    );

    const router = renderApp('/');

    expect(await screen.findByRole('heading', { name: 'My projects' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/');
    expect(screen.getByRole('link', { name: PROJECT.name })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/chat`,
    );
  });

  it('counts projects per role and filters the list by the role chosen', async () => {
    serveMyWork(myWork([EDITING, APPROVING, VIEWING]));
    renderApp('/');
    const summary = await screen.findByRole('group', { name: 'Filter projects by role' });

    const owner = within(summary).getByRole('button', { name: /Product owner on 1 · 3 waiting/ });
    expect(
      within(summary).getByRole('button', { name: /Business analyst on 1 · 6 waiting/ }),
    ).toBeInTheDocument();
    expect(within(summary).getByRole('button', { name: 'Viewer on 1' })).toBeInTheDocument();
    expect(projectNames()).toEqual(['Lab Bookings', 'Library App', 'Sports Hall']);

    await userEvent.click(owner);

    expect(owner).toHaveAttribute('aria-pressed', 'true');
    expect(projectNames()).toEqual(['Library App']);

    await userEvent.click(screen.getByRole('button', { name: 'Clear filter' }));

    expect(owner).toHaveAttribute('aria-pressed', 'false');
    expect(projectNames()).toEqual(['Lab Bookings', 'Library App', 'Sports Hall']);
    expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument();
  });

  it('leaves out a role the user holds on no project', async () => {
    serveMyWork(
      myWork(
        [VIEWING],
        [
          { role: 'approver', projects: 0, waiting: 0 },
          { role: 'editor', projects: 0, waiting: 0 },
          { role: 'viewer', projects: 1, waiting: 0 },
        ],
      ),
    );
    renderApp('/');
    const summary = await screen.findByRole('group', { name: 'Filter projects by role' });

    expect(
      within(summary)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['Viewer on 1']);
  });

  it('lists what waits for each role, each item linking to the page where it is done', async () => {
    serveMyWork(myWork([EDITING, APPROVING, VIEWING]));
    renderApp('/');
    const waiting = await screen.findByRole('region', { name: 'Waiting for you' });

    expect(
      within(waiting).getByRole('link', {
        name: '2 changes waiting for your decision on Library App',
      }),
    ).toHaveAttribute('href', `/projects/${LIBRARY_ID}/changes`);
    expect(
      within(waiting).getByRole('link', {
        name: 'The draft on Library App is ready for your approval',
      }),
    ).toHaveAttribute('href', `/projects/${LIBRARY_ID}/backlog`);
    expect(
      within(waiting).getByRole('link', {
        name: '1 question to answer in the chat on Lab Bookings',
      }),
    ).toHaveAttribute('href', `/projects/${LAB_ID}/chat`);
    expect(
      within(waiting).getByRole('link', {
        name: '3 blockers to clear on the draft of Lab Bookings',
      }),
    ).toHaveAttribute('href', `/projects/${LAB_ID}/backlog`);
    expect(
      within(waiting).getByRole('link', { name: '2 speakers to identify on Lab Bookings' }),
    ).toHaveAttribute('href', `/projects/${LAB_ID}/people`);
    expect(
      within(waiting).getByRole('link', { name: '1 update on Sports Hall in the last 7 days' }),
    ).toHaveAttribute('href', `/projects/${HALL_ID}/activity`);
    expect(within(waiting).getByRole('heading', { name: 'Product owner' })).toBeInTheDocument();
    expect(within(waiting).getByRole('heading', { name: 'Business analyst' })).toBeInTheDocument();
    expect(within(waiting).getByRole('heading', { name: 'Recent activity' })).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('shows a viewer no approver or editor work, only recent activity', async () => {
    serveMyWork(
      myWork(
        [VIEWING],
        [
          { role: 'approver', projects: 0, waiting: 0 },
          { role: 'editor', projects: 0, waiting: 0 },
          { role: 'viewer', projects: 1, waiting: 0 },
        ],
      ),
    );
    renderApp('/');
    const waiting = await screen.findByRole('region', { name: 'Waiting for you' });

    expect(within(waiting).getByText("You're all caught up.")).toBeInTheDocument();
    expect(
      within(waiting)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual(['1 update on Sports Hall in the last 7 days']);
    expect(within(waiting).queryByRole('heading', { name: 'Product owner' })).toBeNull();
    expect(within(waiting).queryByRole('heading', { name: 'Business analyst' })).toBeNull();
  });

  it('says the user is all caught up when nothing waits', async () => {
    serveMyWork(
      myWork(
        [project({ id: LAB_ID, name: 'Lab Bookings', roles: ['editor'] })],
        [
          { role: 'approver', projects: 0, waiting: 0 },
          { role: 'editor', projects: 1, waiting: 0 },
          { role: 'viewer', projects: 0, waiting: 0 },
        ],
      ),
    );
    renderApp('/');

    const waiting = await screen.findByRole('region', { name: 'Waiting for you' });

    expect(within(waiting).getByText("You're all caught up.")).toBeInTheDocument();
    expect(within(waiting).queryAllByRole('link')).toEqual([]);
    expect(screen.getByText('Nothing waiting')).toBeInTheDocument();
  });

  it('shows each project with its role tags, status and waiting count', async () => {
    serveMyWork(myWork([EDITING, APPROVING]));
    renderApp('/');
    const list = await screen.findByRole('region', { name: 'My projects' });

    const [lab, library] = within(list).getAllByRole('listitem');
    expect(lab).toHaveTextContent('Lab Bookings');
    expect(lab).toHaveTextContent('Business analyst');
    expect(lab).toHaveTextContent('No baseline yet');
    expect(lab).toHaveTextContent('6 waiting');
    expect(library).toHaveTextContent('Product owner');
    expect(library).toHaveTextContent('Draft in progress');
    expect(library).toHaveTextContent('3 waiting');
  });

  it('works at phone width', async () => {
    setNarrowViewport(true);
    serveMyWork(myWork([EDITING, APPROVING, VIEWING]));

    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'Waiting for you' })).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('offers a new project when the user belongs to none', async () => {
    serveMyWork(
      myWork(
        [],
        [
          { role: 'approver', projects: 0, waiting: 0 },
          { role: 'editor', projects: 0, waiting: 0 },
          { role: 'viewer', projects: 0, waiting: 0 },
        ],
      ),
    );

    renderApp('/');

    expect(await screen.findByRole('heading', { name: 'No projects yet' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Project' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'New project' })).toBeInTheDocument();
  });

  it('creates the first project and opens it when the user is done', async () => {
    let created = false;
    server.use(
      http.get('*/api/v1/me/work', () =>
        HttpResponse.json(
          myWork(
            created ? [project({ id: PROJECT_ID, name: PROJECT.name, roles: ['editor'] })] : [],
          ),
        ),
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

    // The page now lists one project, but the modal stays open on its second step.
    expect(await screen.findByLabelText('Step 2 of 2')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/');

    await userEvent.click(screen.getByRole('button', { name: 'Open project' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/chat`);
    });
  });

  it("shows the server's message and the API status when the projects cannot be loaded", async () => {
    server.use(
      http.get('*/api/v1/me/work', () =>
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
    renderApp('/nowhere');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Page not found' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go to your projects' })).toHaveAttribute('href', '/');
  });
});
