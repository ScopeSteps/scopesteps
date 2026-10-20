import { configure, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { components } from '@scopesteps/api-client';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT, PROJECT_ID, REVIEWER, BRIEF, VIEWER } from '@/test/fixtures';
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
    http.get(`${API}/projects/:projectId/messages`, () =>
      HttpResponse.json({ messages: [], next_cursor: null, active_run: null }),
    ),
    http.get(`${API}/projects/:projectId/sources`, ({ params }) => {
      sourceRequests.push(String(params.projectId));
      return HttpResponse.json({ source_versions: [] });
    }),
    http.get(`${API}/projects/:projectId/people`, () =>
      HttpResponse.json({ people: [], unconfirmed_speakers: [] }),
    ),
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
    await userEvent.keyboard('{End}');
    expect(screen.getByRole('menuitem', { name: 'Project settings' })).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitemradio', { name: PROJECT.name })).toHaveFocus();
    await userEvent.keyboard('{ArrowUp}');
    expect(screen.getByRole('menuitem', { name: 'Project settings' })).toHaveFocus();
    await userEvent.keyboard('{Home}');
    expect(screen.getByRole('menuitemradio', { name: PROJECT.name })).toHaveFocus();
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(card).toHaveFocus();
  });

  it("stays open under React's development checks, which re-run its effects", async () => {
    configure({ reactStrictMode: true });
    try {
      renderApp(`/projects/${PROJECT_ID}/chat`);
      const menu = await openMenu();

      expect(await within(menu).findByRole('menuitemradio', { name: PROJECT.name })).toHaveFocus();
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(screen.getByRole('menu', { name: 'Projects' })).toBeInTheDocument();
    } finally {
      configure({ reactStrictMode: false });
    }
  });

  it('closes when Tab moves focus out of it', async () => {
    renderApp(`/projects/${PROJECT_ID}/chat`);
    await openMenu();
    await screen.findByRole('menuitemradio', { name: PROJECT.name });

    await userEvent.keyboard('{End}');
    await userEvent.tab();

    await waitFor(() => {
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });
  });

  it('describes the menu as loading until the projects arrive', async () => {
    server.use(http.get(`${API}/projects`, () => new Promise<never>(() => undefined)));
    renderApp(`/projects/${PROJECT_ID}/chat`);

    const menu = await openMenu();

    expect(menu).toHaveAccessibleDescription('Loading your projects…');
    expect(menu).toHaveFocus();
    await expectNoAccessibilityViolations();
  });

  it('offers a retry from the keyboard when the projects cannot be listed', async () => {
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

    const retry = await within(menu).findByRole('menuitem', { name: 'Try again' });
    expect(retry).toHaveAccessibleDescription('Could not load your projects. Try again shortly.');
    await waitFor(() => {
      expect(retry).toHaveFocus();
    });
    await expectNoAccessibilityViolations();
    healthy = true;
    await userEvent.keyboard('{Enter}');

    const current = await within(menu).findByRole('menuitemradio', { name: PROJECT.name });
    await waitFor(() => {
      expect(current).toHaveFocus();
    });
    expect(screen.getByRole('menu', { name: 'Projects' })).toBeInTheDocument();
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
    expect(within(dialog).getByLabelText('Upload .txt or .md files')).toBeInTheDocument();
    expect(screen.queryByText(/Or use the sample/)).not.toBeInTheDocument();
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
      "Say who's who in your transcripts",
      'Start the agent run',
      'Answer questions, then review the draft backlog',
    ]);
    expect(steps.map((step) => step.getAttribute('aria-current'))).toEqual([
      'step',
      null,
      null,
      null,
    ]);
  });

  async function reachStepTwo() {
    server.use(
      http.post(`${API}/projects`, () =>
        HttpResponse.json({ ...PROJECT, id: NEW_ID, name: 'Campus Bike Share' }, { status: 201 }),
      ),
      http.get(`${API}/projects/${NEW_ID}`, () =>
        HttpResponse.json({ ...PROJECT, id: NEW_ID, name: 'Campus Bike Share' }),
      ),
    );
    const router = renderApp(`/projects/${PROJECT_ID}/backlog`);
    const dialog = await openNewProject();
    await userEvent.type(
      within(dialog).getByRole('textbox', { name: 'Project name' }),
      'Campus Bike Share{Enter}',
    );
    await within(dialog).findByLabelText('Step 2 of 2');
    return { router, dialog };
  }

  function recordNewProjectUploads(respond: () => Response) {
    const received: string[][] = [];
    server.use(
      http.post(`${API}/projects/${NEW_ID}/sources`, async ({ request }) => {
        const form = await request.formData();
        const parts: string[] = [];
        for (const [kind, value] of form.entries()) {
          parts.push(`${kind}: ${typeof value === 'string' ? value : value.name}`);
        }
        received.push(parts);
        return respond();
      }),
    );
    return received;
  }

  it('adds several files in step 2 in one upload, then opens the project', async () => {
    const received = recordNewProjectUploads(() =>
      HttpResponse.json({ source_versions: [BRIEF] }, { status: 201 }),
    );
    const { router, dialog } = await reachStepTwo();

    fireEvent.change(within(dialog).getByLabelText('Upload .txt or .md files'), {
      target: {
        files: [
          new File(['Students book rooms.'], 'brief.md'),
          new File(['Dana: single slots.'], 'call.txt'),
          new File(['Clubs want weekly slots.'], 'clubs.md'),
        ],
      },
    });
    expect(
      within(within(dialog).getByRole('list', { name: 'Files to add' })).getAllByRole('listitem'),
    ).toHaveLength(3);
    await expectNoAccessibilityViolations();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add 3 sources and open' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${NEW_ID}/chat`);
    });
    expect(received).toEqual([
      ['brief: brief.md', 'transcript: call.txt', 'supporting_document: clubs.md'],
    ]);
  });

  it("keeps step 2 open with the API's reason when the upload is refused", async () => {
    recordNewProjectUploads(() =>
      HttpResponse.json(
        errorBody('SOURCE_WORD_LIMIT_EXCEEDED', 'The sources would exceed 6,000 words.'),
        { status: 422 },
      ),
    );
    const { router, dialog } = await reachStepTwo();

    fireEvent.change(within(dialog).getByLabelText('Upload .txt or .md files'), {
      target: { files: [new File(['a b c'], 'brief.md'), new File(['d e'], 'call.txt')] },
    });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Add 2 sources and open' }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent(
      'The sources would exceed 6,000 words.',
    );
    expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/backlog`);
  });

  it('skips step 2 without uploading anything', async () => {
    const received = recordNewProjectUploads(() =>
      HttpResponse.json({ source_versions: [] }, { status: 201 }),
    );
    const { router, dialog } = await reachStepTwo();

    fireEvent.change(within(dialog).getByLabelText('Upload .txt or .md files'), {
      target: { files: [new File(['a'], 'brief.md')] },
    });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Remove brief.md' }));
    await userEvent.click(within(dialog).getByRole('button', { name: 'Open project' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${NEW_ID}/chat`);
    });
    expect(received).toHaveLength(0);
  });

  it("marks the setup steps from the project's sources and scope status", async () => {
    server.use(
      http.get(`${API}/projects/${NEW_ID}`, () =>
        HttpResponse.json({ ...PROJECT, id: NEW_ID, name: 'Campus Bike Share' }),
      ),
      http.get(`${API}/projects/${NEW_ID}/sources`, () =>
        HttpResponse.json({ source_versions: [BRIEF] }),
      ),
    );

    renderApp(`/projects/${NEW_ID}/chat`);

    const intro = await screen.findByRole('region', { name: 'New chat for Campus Bike Share' });
    await within(intro).findByText(/1 source added/);
    await within(intro).findByText('Everyone who speaks in your transcripts is identified');
    const steps = within(intro).getAllByRole('listitem');
    expect(steps[0]).toHaveTextContent('(done)');
    expect(steps[1]).toHaveTextContent('(done)');
    expect(steps.map((step) => step.getAttribute('aria-current'))).toEqual([
      null,
      null,
      'step',
      null,
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
    expect(within(dialog).getByRole('heading', { name: 'Project settings' })).toHaveFocus();
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
