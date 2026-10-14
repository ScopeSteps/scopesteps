import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { components } from '@scopesteps/api-client';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT, PROJECT_ID, REVIEWER, VIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { resetViewport, setNarrowViewport } from '@/test/viewport';

type ProjectDetail = components['schemas']['ProjectDetailResponse'];
type ProjectSummary = components['schemas']['ProjectResponse'];

const SECOND_ID = '019a3a5e-0000-7000-8000-000000000009';
const NEW_ID = '019a3a5e-0000-7000-8000-00000000000a';
const SECOND: ProjectDetail = {
  ...PROJECT,
  id: SECOND_ID,
  name: 'Campus Parking Permits',
  status: {
    state: 'baseline',
    baseline_version: 2,
    baseline_version_id: '019a3a5e-0000-7000-8000-0000000000e9',
    open_version_id: null,
  },
};
const OTHER_MEMBER = {
  user_id: '019a3a5e-0000-7000-8000-000000000003',
  display_name: 'Riley Approver',
  job_title: 'Head of Facilities',
  roles: ['approver' as const],
};

function summary(project: ProjectDetail): ProjectSummary {
  const { id, name, created_at, revision, roles, status } = project;
  return { id, name, created_at, revision, roles, status };
}

function sidebar() {
  return screen.getByRole('complementary', { name: 'Main navigation' });
}

async function projectButton(name = PROJECT.name) {
  return within(sidebar()).findByRole('button', { name: new RegExp(`^Project ${name}`) });
}

async function openMenu() {
  await userEvent.click(await projectButton());
  return screen.getByRole('menu', { name: 'Projects' });
}

async function openProjectSettings() {
  await openMenu();
  await userEvent.click(screen.getByRole('menuitem', { name: 'Project settings' }));
  return screen.findByRole('dialog', { name: 'Project settings' });
}

let sourceRequests: string[];

beforeEach(() => {
  window.localStorage.clear();
  sourceRequests = [];
  // The first matching handler answers, so these come before the defaults they override.
  server.use(
    http.get(`${API}/projects`, () =>
      HttpResponse.json({ projects: [summary(PROJECT), summary(SECOND)] }),
    ),
    http.get(`${API}/projects/${SECOND_ID}`, () => HttpResponse.json(SECOND)),
    http.get(`${API}/projects/:projectId/sources`, ({ params }) => {
      sourceRequests.push(String(params.projectId));
      return HttpResponse.json({ source_versions: [] });
    }),
    http.get(`${API}/projects/:projectId/members`, () =>
      HttpResponse.json({
        members: [
          {
            user_id: REVIEWER.id,
            display_name: REVIEWER.display_name,
            job_title: '',
            roles: ['editor'],
          },
          OTHER_MEMBER,
        ],
      }),
    ),
    ...projectHandlers(),
  );
});

afterEach(() => {
  resetViewport();
});

describe('project switcher', () => {
  it("names the project in view with the API's scope status", async () => {
    renderApp(`/projects/${SECOND_ID}/sources`);

    expect(await projectButton(SECOND.name)).toHaveTextContent('Baseline v2 approved');
  });

  it('lists the projects by name and marks the current one', async () => {
    renderApp(`/projects/${PROJECT_ID}/sources`);

    const menu = await openMenu();

    const current = await within(menu).findByRole('menuitemradio', { name: PROJECT.name });
    expect(current).toHaveAttribute('aria-checked', 'true');
    expect(current).toHaveFocus();
    expect(within(menu).getByRole('menuitemradio', { name: SECOND.name })).toHaveAttribute(
      'aria-checked',
      'false',
    );
    expect(within(menu).getByRole('menuitem', { name: 'New project' })).toBeInTheDocument();
    expect(within(menu).queryByText(/demo/i)).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('switches to the same page of the other project, and its data follows', async () => {
    const router = renderApp(`/projects/${PROJECT_ID}/sources?version=${PROJECT_ID}`);
    const menu = await openMenu();

    await userEvent.click(await within(menu).findByRole('menuitemradio', { name: SECOND.name }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${SECOND_ID}/sources`);
    });
    expect(router.state.location.search).toBe('');
    expect(await projectButton(SECOND.name)).toBeInTheDocument();
    await waitFor(() => {
      expect(sourceRequests).toContain(SECOND_ID);
    });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('is driven from the keyboard, and Escape returns focus to the card', async () => {
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const card = await projectButton();
    card.focus();

    await userEvent.keyboard('{Enter}');
    await screen.findByRole('menuitemradio', { name: PROJECT.name });
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitemradio', { name: SECOND.name })).toHaveFocus();
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(card).toHaveFocus();
  });

  it('offers a retry when the projects cannot be listed', async () => {
    let healthy = false;
    server.use(
      http.get(`${API}/projects`, () =>
        healthy
          ? HttpResponse.json({ projects: [summary(PROJECT)] })
          : HttpResponse.json(errorBody('UNAVAILABLE', 'Try again shortly.', true), {
              status: 503,
            }),
      ),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const menu = await openMenu();

    expect(await within(menu).findByText(/Could not load your projects/)).toBeInTheDocument();
    healthy = true;
    await userEvent.click(within(menu).getByRole('button', { name: 'Try again' }));

    expect(await within(menu).findByRole('menuitemradio', { name: PROJECT.name })).toBeVisible();
  });

  it('says so when the project in the address cannot be opened', async () => {
    server.use(
      http.get(`${API}/projects/${SECOND_ID}`, () =>
        HttpResponse.json(errorBody('NOT_FOUND', 'No such project.'), { status: 404 }),
      ),
    );

    renderApp(`/projects/${SECOND_ID}/chat`);

    expect(await projectButton('Project unavailable')).toBeInTheDocument();
  });

  it('keeps no project data in browser storage', async () => {
    const router = renderApp(`/projects/${PROJECT_ID}/sources`);
    await userEvent.click(
      await within(await openMenu()).findByRole('menuitemradio', { name: SECOND.name }),
    );
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${SECOND_ID}/sources`);
    });

    expect(Object.keys(window.localStorage)).toEqual(['scopesteps:preferences']);
    expect(window.sessionStorage).toHaveLength(0);
  });
});

describe('new project', () => {
  async function openNewProject() {
    await openMenu();
    await userEvent.click(screen.getByRole('menuitem', { name: 'New project' }));
    return screen.findByRole('dialog', { name: 'New project' });
  }

  it('asks for a name, then offers sources, and opens the project without any', async () => {
    let body: unknown = null;
    let idempotencyKey: string | null = null;
    server.use(
      http.post(`${API}/projects`, async ({ request }) => {
        body = await request.json();
        idempotencyKey = request.headers.get('Idempotency-Key');
        return HttpResponse.json(
          { ...PROJECT, id: NEW_ID, name: 'Campus Bike Share' },
          {
            status: 201,
          },
        );
      }),
      http.get(`${API}/projects/${NEW_ID}`, () =>
        HttpResponse.json({ ...PROJECT, id: NEW_ID, name: 'Campus Bike Share' }),
      ),
    );
    const router = renderApp(`/projects/${PROJECT_ID}/backlog`);
    const dialog = await openNewProject();

    expect(within(dialog).getByLabelText('Step 1 of 2')).toBeInTheDocument();
    expect(within(dialog).getByRole('heading', { name: 'New project' })).toHaveFocus();
    await expectNoAccessibilityViolations();
    await userEvent.type(
      within(dialog).getByRole('textbox', { name: 'Project name' }),
      'Campus Bike Share{Enter}',
    );

    expect(await within(dialog).findByLabelText('Step 2 of 2')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Open project' })).toHaveFocus();
    expect(body).toEqual({ name: 'Campus Bike Share' });
    expect(idempotencyKey).toMatch(/^[0-9a-f-]{36}$/);
    expect(
      await screen.findByText('No sources yet. A project can start without any.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add sources' })).toBeInTheDocument();
    await expectNoAccessibilityViolations();

    await userEvent.click(screen.getByRole('button', { name: 'Open project' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${NEW_ID}/chat`);
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { name: 'New chat for Campus Bike Share' }),
    ).toBeInTheDocument();
    const steps = screen.getAllByRole('listitem').filter((item) => item.closest('ol'));
    expect(steps.map((step) => step.querySelector('strong')?.textContent)).toEqual([
      'Add a project brief and a meeting transcript',
      'Start the agent run',
      'Answer questions, then review the draft backlog',
    ]);
  });

  it('asks for a name before calling the API', async () => {
    let requests = 0;
    server.use(
      http.post(`${API}/projects`, () => {
        requests += 1;
        return HttpResponse.json(PROJECT, { status: 201 });
      }),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openNewProject();

    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Project name' }), '   ');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));

    const field = within(dialog).getByRole('textbox', { name: 'Project name' });
    expect(field).toHaveAccessibleDescription(expect.stringContaining('Enter a project name.'));
    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(requests).toBe(0);
  });

  it("shows the API's reason when it refuses the name", async () => {
    server.use(
      http.post(`${API}/projects`, () =>
        HttpResponse.json(
          errorBody('PROJECT_NAME_INVALID', 'A project name can be at most 80 characters.'),
          { status: 422 },
        ),
      ),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openNewProject();

    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Project name' }), 'Too long');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));

    expect(
      await within(dialog).findByText('A project name can be at most 80 characters.'),
    ).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Step 1 of 2')).toBeInTheDocument();
  });

  it('keeps the same idempotency key when retrying after a server failure', async () => {
    const keys: (string | null)[] = [];
    server.use(
      http.post(`${API}/projects`, ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key'));
        return keys.length === 1
          ? HttpResponse.json(errorBody('UNAVAILABLE', 'Try again shortly.', true), {
              status: 503,
            })
          : HttpResponse.json({ ...PROJECT, id: NEW_ID }, { status: 201 });
      }),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openNewProject();
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Project name' }), 'Retry');

    await userEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Try again shortly.');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Continue' }));

    expect(await within(dialog).findByLabelText('Step 2 of 2')).toBeInTheDocument();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('opens from the drawer on a narrow screen', async () => {
    setNarrowViewport(true);
    renderApp(`/projects/${PROJECT_ID}/chat`);
    await userEvent.click(await screen.findByRole('button', { name: 'Open menu' }));

    await openNewProject();

    expect(screen.queryByRole('complementary')).not.toBeInTheDocument();
  });
});

describe('project settings', () => {
  it('renames the project with the revision it was opened on', async () => {
    let body: unknown = null;
    let renamed = false;
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json(
          renamed ? { ...PROJECT, name: 'Study Space Booking', revision: 2 } : PROJECT,
        ),
      ),
      http.patch(`${API}/projects/${PROJECT_ID}`, async ({ request }) => {
        body = await request.json();
        renamed = true;
        return HttpResponse.json({ ...PROJECT, name: 'Study Space Booking', revision: 2 });
      }),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openProjectSettings();
    const field = within(dialog).getByRole('textbox', { name: 'Project name' });
    expect(field).toHaveValue(PROJECT.name);
    expect(field).toHaveAttribute('maxlength', String(PROJECT.limits.project_name_max_chars));
    await expectNoAccessibilityViolations();

    await userEvent.clear(field);
    await userEvent.type(field, 'Study Space Booking');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(body).toEqual({ name: 'Study Space Booking', expected_revision: 1 });
    expect(await projectButton('Study Space Booking')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Project settings saved.');
  });

  it('shows the limits and the members the API reports', async () => {
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openProjectSettings();

    const limits = within(dialog).getByRole('region', { name: 'Limits for this project' });
    expect(limits).toHaveTextContent(
      'TXT or Markdown, up to 512 KB each and 6,000 words per upload',
    );
    expect(limits).toHaveTextContent('6 model turns, 8 tool calls, 2 question rounds');
    expect(limits).toHaveTextContent('Up to 2 epics and 8 stories');
    const members = within(dialog).getByRole('region', { name: 'Members' });
    expect(await within(members).findByText(OTHER_MEMBER.display_name)).toBeInTheDocument();
    expect(within(members).getByText('Head of Facilities')).toBeInTheDocument();
    expect(within(members).getByText('Product owner')).toBeInTheDocument();
    expect(within(members).getByText('Business analyst')).toBeInTheDocument();
  });

  it("shows the API's reason when it refuses the new name", async () => {
    server.use(
      http.patch(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json(errorBody('PROJECT_NAME_INVALID', 'Use printable characters only.'), {
          status: 422,
        }),
      ),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openProjectSettings();
    const field = within(dialog).getByRole('textbox', { name: 'Project name' });

    await userEvent.clear(field);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    expect(field).toHaveAccessibleDescription(expect.stringContaining('Enter a project name.'));

    await userEvent.type(field, 'Odd name');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(await within(dialog).findByText('Use printable characters only.')).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Project settings' })).toBeInTheDocument();
  });

  it('says someone else renamed it, and reloads the current name on request', async () => {
    let serverProject = PROJECT;
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}`, () => HttpResponse.json(serverProject)),
      http.patch(`${API}/projects/${PROJECT_ID}`, () => {
        serverProject = { ...PROJECT, name: 'Renamed Elsewhere', revision: 2 };
        return HttpResponse.json(
          {
            ...errorBody('PROJECT_CHANGED', 'The project changed.'),
            details: { current_revision: 2 },
          },
          { status: 409 },
        );
      }),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openProjectSettings();
    const field = within(dialog).getByRole('textbox', { name: 'Project name' });
    await userEvent.type(field, ' 2');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'Someone else changed this project while you were editing.',
    );
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeDisabled();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Reload' }));

    await waitFor(() => {
      expect(field).toHaveValue('Renamed Elsewhere');
    });
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeEnabled();
  });

  it('is read-only for a viewer', async () => {
    let renames = 0;
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({ ...PROJECT, roles: ['viewer'] }),
      ),
      http.patch(`${API}/projects/${PROJECT_ID}`, () => {
        renames += 1;
        return HttpResponse.json(PROJECT);
      }),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openProjectSettings();

    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
    expect(within(dialog).getByText(PROJECT.name)).toBeInTheDocument();
    expect(within(dialog).getByText(/You have view-only access/)).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(within(dialog).getByRole('region', { name: 'Limits for this project' })).toBeVisible();
    await expectNoAccessibilityViolations();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Done' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(renames).toBe(0);
  });

  it('lets an approver without the editor role rename', async () => {
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({ ...PROJECT, roles: ['approver'] }),
      ),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const dialog = await openProjectSettings();

    expect(within(dialog).getByRole('textbox', { name: 'Project name' })).toBeEnabled();
  });
});
