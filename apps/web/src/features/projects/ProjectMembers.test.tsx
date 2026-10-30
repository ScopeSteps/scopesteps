import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { APPROVER, errorBody, PROJECT, PROJECT_ID, REVIEWER, VIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Schemas = components['schemas'];

const MEMBERS_URL = `${API}/projects/${PROJECT_ID}/members`;
const INVITATIONS_URL = `${API}/projects/${PROJECT_ID}/invitations`;
const EDITOR_ID = '019a3a5e-0000-7000-8000-0000000000c2';
const INVITATION_ID = '019a3a5e-0000-7000-8000-0000000000c9';
const LINK = 'https://app.test/invite/a-synthetic-link-token';

const ME: Schemas['ProjectMemberResponse'] = {
  user_id: REVIEWER.id,
  display_name: APPROVER.display_name,
  job_title: '',
  roles: ['approver'],
  revision: 1,
};
const EDITOR: Schemas['ProjectMemberResponse'] = {
  user_id: EDITOR_ID,
  display_name: 'Eli Editor',
  job_title: 'Analyst',
  roles: ['editor'],
  revision: 3,
};
const INVITATION: Schemas['InvitationResponse'] = {
  id: INVITATION_ID,
  email: 'pending@example.test',
  roles: ['viewer'],
  invited_by: REVIEWER.id,
  invited_by_name: APPROVER.display_name,
  created_at: '2026-10-27T09:00:00Z',
  expires_at: '2026-11-03T09:00:00Z',
  expired: false,
};

interface Sent {
  method: string;
  path: string;
  body: unknown;
}

function as(user: Schemas['CurrentUserResponse'], roles: Schemas['Role'][]) {
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json(user)),
    http.get(`${API}/projects/${PROJECT_ID}`, () => HttpResponse.json({ ...PROJECT, roles })),
    http.get(`${API}/projects`, () =>
      HttpResponse.json({
        projects: [
          {
            id: PROJECT.id,
            name: PROJECT.name,
            created_at: PROJECT.created_at,
            revision: 1,
            roles,
            status: PROJECT.status,
          },
        ],
      }),
    ),
  );
}

/** Records every membership command, answering each with `respond`. */
function record(respond: (sent: Sent) => Response | undefined = () => undefined) {
  const sent: Sent[] = [];
  server.use(
    http.all(`${API}/projects/${PROJECT_ID}/:rest*`, async ({ request }) => {
      const path = new URL(request.url).pathname;
      if (request.method === 'GET' || !/members|invitations/.test(path)) {
        return undefined;
      }
      const body: unknown =
        request.method === 'POST' || request.method === 'PUT'
          ? await request.json().catch(() => null)
          : null;
      const each = { method: request.method, path, body };
      sent.push(each);
      return respond(each) ?? new HttpResponse(null, { status: 204 });
    }),
  );
  return sent;
}

async function openMembers() {
  const sidebar = screen.getByRole('complementary', { name: 'Main navigation' });
  await userEvent.click(
    await within(sidebar).findByRole('button', { name: new RegExp(`^Project ${PROJECT.name}`) }),
  );
  await userEvent.click(screen.getByRole('menuitem', { name: 'Project settings' }));
  const dialog = await screen.findByRole('dialog', { name: /Project settings|Rename/ });
  const panel = within(within(dialog).getByRole('region', { name: 'Members' }));
  await panel.findByText(EDITOR.display_name);
  return panel;
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
  server.use(
    http.get(MEMBERS_URL, () => HttpResponse.json({ members: [ME, EDITOR] })),
    http.get(INVITATIONS_URL, () => HttpResponse.json({ invitations: [INVITATION] })),
  );
});

describe('The members panel for an approver', () => {
  it('invites an email with the roles chosen, emailed by default', async () => {
    as(APPROVER, ['approver']);
    const sent = record(() =>
      HttpResponse.json(
        {
          invitation: { ...INVITATION, email: 'new@example.test', roles: ['viewer', 'editor'] },
          link: null,
          email_sent: true,
        },
        { status: 201 },
      ),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(panel.getByRole('button', { name: 'Invite people' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Invite people' }));
    expect(dialog.getByRole('checkbox', { name: /^Viewer/ })).toBeChecked();
    expect(dialog.getByRole('checkbox', { name: 'Email the invitation' })).toBeChecked();
    await userEvent.type(dialog.getByRole('textbox', { name: 'Email' }), 'new@example.test');
    await userEvent.click(dialog.getByRole('checkbox', { name: /^Editor/ }));
    await userEvent.click(dialog.getByRole('button', { name: 'Invite' }));

    expect(await screen.findByText('We emailed an invitation to new@example.test.')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(panel.getByRole('button', { name: 'Invite people' })).toHaveFocus();
    expect(sent).toEqual([
      {
        method: 'POST',
        path: `/api/v1/projects/${PROJECT_ID}/members`,
        body: { email: 'new@example.test', roles: ['viewer', 'editor'], send_email: true },
      },
    ]);
    await expectNoAccessibilityViolations();
  });

  it('invites without email and copies the link it returns', async () => {
    as(APPROVER, ['approver']);
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const sent = record(() =>
      HttpResponse.json({ invitation: INVITATION, link: LINK, email_sent: false }, { status: 201 }),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(panel.getByRole('button', { name: 'Invite people' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Invite people' }));
    await userEvent.type(dialog.getByRole('textbox', { name: 'Email' }), 'pending@example.test');
    await userEvent.click(dialog.getByRole('checkbox', { name: 'Email the invitation' }));
    await userEvent.click(dialog.getByRole('button', { name: 'Invite' }));
    const ready = within(await screen.findByRole('dialog', { name: 'Invitation ready' }));
    await userEvent.click(ready.getByRole('button', { name: 'Copy link' }));

    expect(writeText).toHaveBeenCalledWith(LINK);
    expect(await ready.findByText('Copied. Works once, expires in 7 days.')).toBeVisible();
    expect(sent[0]?.body).toMatchObject({ send_email: false });
  });

  it('shows a pending invitation, makes a new link after warning, resends and cancels it', async () => {
    as(APPROVER, ['approver']);
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const sent = record(({ path, method }) => {
      if (path.endsWith('/link')) {
        return HttpResponse.json({ invitation: INVITATION, link: LINK });
      }
      if (path.endsWith('/email')) {
        return HttpResponse.json(INVITATION, { status: 202 });
      }
      return method === 'DELETE' ? new HttpResponse(null, { status: 204 }) : undefined;
    });
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    const pending = within(await panel.findByRole('list', { name: 'Pending invitations' }));
    expect(pending.getByText('pending@example.test')).toBeVisible();
    expect(pending.getByText('Pending')).toBeVisible();
    await userEvent.click(
      pending.getByRole('button', { name: 'Copy a new link for pending@example.test' }),
    );
    const linkDialog = within(await screen.findByRole('dialog', { name: /^Link for/ }));
    expect(linkDialog.getByText(/stops working/)).toBeVisible();
    await userEvent.click(linkDialog.getByRole('button', { name: 'Make a new link' }));
    await userEvent.click(await linkDialog.findByRole('button', { name: 'Copy link' }));
    expect(writeText).toHaveBeenCalledWith(LINK);
    await userEvent.click(linkDialog.getByRole('button', { name: 'Done' }));
    await userEvent.click(
      pending.getByRole('button', { name: 'Email the invitation to pending@example.test again' }),
    );
    expect(await panel.findByText('Invitation emailed to pending@example.test.')).toBeVisible();
    await userEvent.click(
      pending.getByRole('button', { name: 'Cancel the invitation for pending@example.test' }),
    );

    await waitFor(() => {
      expect(sent.map((s) => `${s.method} ${s.path.split(INVITATION_ID)[1] ?? ''}`)).toEqual([
        'POST /link',
        'POST /email',
        'DELETE ',
      ]);
    });
  });

  it('changes a member’s roles at the revision on screen', async () => {
    as(APPROVER, ['approver']);
    const sent = record(() => HttpResponse.json({ ...EDITOR, roles: ['editor', 'approver'] }));
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(panel.getByRole('button', { name: 'Change roles of Eli Editor' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Roles of Eli Editor' }));
    expect(dialog.getByRole('checkbox', { name: /^Editor/ })).toBeChecked();
    await userEvent.click(dialog.getByRole('checkbox', { name: /^Approver/ }));
    await userEvent.click(dialog.getByRole('button', { name: 'Save roles' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Roles of Eli Editor' })).toBeNull();
    });
    expect(sent).toEqual([
      {
        method: 'PUT',
        path: `/api/v1/projects/${PROJECT_ID}/members/${EDITOR_ID}/roles`,
        body: { roles: ['editor', 'approver'], expected_revision: 3 },
      },
    ]);
  });

  it('removes a member only after confirming', async () => {
    as(APPROVER, ['approver']);
    const sent = record();
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(panel.getByRole('button', { name: 'Remove Eli Editor' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Remove Eli Editor?' }));
    expect(dialog.getByText(/loses access to this project now/)).toBeVisible();
    expect(dialog.getByText(/past work stays/)).toBeVisible();
    expect(sent).toEqual([]);
    await userEvent.click(dialog.getByRole('button', { name: 'Remove' }));

    await waitFor(() => {
      expect(sent).toEqual([
        {
          method: 'DELETE',
          path: `/api/v1/projects/${PROJECT_ID}/members/${EDITOR_ID}`,
          body: null,
        },
      ]);
    });
  });

  it.each([
    [
      'LAST_APPROVER',
      409,
      'A project needs at least one approver. Make someone else approver first.',
    ],
    [
      'MEMBER_CHANGED',
      409,
      "This member's roles were changed meanwhile. Reload the members and try again.",
    ],
  ])('says why a role change was refused (%s)', async (code, status, message) => {
    as(APPROVER, ['approver']);
    record(() => HttpResponse.json(errorBody(code, message), { status }));
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(panel.getByRole('button', { name: 'Change roles of Eli Editor' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Roles of Eli Editor' }));
    await userEvent.click(dialog.getByRole('checkbox', { name: /^Viewer/ }));
    await userEvent.click(dialog.getByRole('button', { name: 'Save roles' }));

    expect(await dialog.findByRole('alert')).toHaveTextContent(message);
  });

  it.each([
    ['RATE_LIMITED', 429, 'Too many attempts. Wait a while, then try again.'],
    [
      'EMAIL_FAILED',
      502,
      'The email could not be sent. Try again later, or copy the link instead.',
    ],
  ])('says why an invitation email was refused (%s)', async (code, status, message) => {
    as(APPROVER, ['approver']);
    record(() => HttpResponse.json(errorBody(code, message, true), { status }));
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(
      panel.getByRole('button', { name: 'Email the invitation to pending@example.test again' }),
    );

    expect(await panel.findByRole('alert')).toHaveTextContent(message);
  });
});

describe('The members panel for everyone else', () => {
  it.each([
    ['an editor', REVIEWER, ['editor'] as Schemas['Role'][]],
    ['a viewer', VIEWER, ['viewer'] as Schemas['Role'][]],
  ])('shows %s the members read-only, with only Leave project', async (_, user, roles) => {
    as(user, roles);
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    expect(panel.queryByRole('button', { name: 'Invite people' })).toBeNull();
    expect(panel.queryByRole('button', { name: /^Change roles/ })).toBeNull();
    expect(panel.queryByRole('button', { name: /^Remove/ })).toBeNull();
    expect(panel.queryByRole('list', { name: 'Pending invitations' })).toBeNull();
    expect(panel.getByRole('button', { name: 'Leave project' })).toBeVisible();
  });

  it('leaves after confirming, lands on the home page and no longer lists the project', async () => {
    as(REVIEWER, ['editor']);
    let left = false;
    const sent = record(() => {
      left = true;
      return undefined;
    });
    const listed = {
      id: PROJECT.id,
      name: PROJECT.name,
      created_at: PROJECT.created_at,
      revision: 1,
      roles: ['editor' as const],
      status: PROJECT.status,
    };
    const roles = (projects: number) => [
      { role: 'approver' as const, projects: 0, waiting: 0 },
      { role: 'editor' as const, projects, waiting: 0 },
      { role: 'viewer' as const, projects: 0, waiting: 0 },
    ];
    server.use(
      http.get(`${API}/projects`, () => HttpResponse.json({ projects: left ? [] : [listed] })),
      http.get(`${API}/me/work`, () =>
        HttpResponse.json({
          projects: left
            ? []
            : [
                {
                  ...listed,
                  waiting: 0,
                  approver: null,
                  editor: { open_questions: 0, draft_blockers: 0, unconfirmed_speakers: 0 },
                  recent_activity: null,
                },
              ],
          roles: roles(left ? 0 : 1),
          activity_window_days: 7,
        }),
      ),
    );
    const router = renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(panel.getByRole('button', { name: 'Leave project' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Leave this project?' }));
    await userEvent.click(dialog.getByRole('button', { name: 'Leave project' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
    expect(sent[0]?.path).toBe(`/api/v1/projects/${PROJECT_ID}/members/${REVIEWER.id}`);
    expect(await screen.findByRole('button', { name: /New project/ })).toBeVisible();
    expect(screen.queryByRole('link', { name: new RegExp(PROJECT.name) })).toBeNull();
  });

  it('tells the last approver why they cannot leave', async () => {
    as(APPROVER, ['approver']);
    record(() =>
      HttpResponse.json(
        errorBody(
          'LAST_APPROVER',
          'A project needs at least one approver. Make someone else approver first.',
        ),
        { status: 409 },
      ),
    );
    renderApp(`/projects/${PROJECT_ID}/chat`);
    const panel = await openMembers();

    await userEvent.click(panel.getByRole('button', { name: 'Leave project' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Leave this project?' }));
    await userEvent.click(dialog.getByRole('button', { name: 'Leave project' }));

    expect(await dialog.findByRole('alert')).toHaveTextContent('Make someone else approver first.');
  });
});
