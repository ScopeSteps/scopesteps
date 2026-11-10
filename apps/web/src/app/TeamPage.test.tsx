import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { membership, PERMISSIONS, PROJECT, PROJECT_ID, REVIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Member = components['schemas']['ProjectMemberResponse'];
type Role = 'viewer' | 'editor' | 'approver';

const PAGE = `/projects/${PROJECT_ID}/team`;
const MEMBERS_URL = `${API}/projects/${PROJECT_ID}/members`;
const DANA_ID = '019a3a5e-0000-7000-8000-0000000000d2';
const SAM_ID = '019a3a5e-0000-7000-8000-0000000000d3';

function member(overrides: Partial<Member>): Member {
  return {
    user_id: REVIEWER.id,
    display_name: REVIEWER.display_name,
    job_title: '',
    role: 'approver',
    joined_at: '2026-10-01T09:00:00Z',
    waiting: 0,
    revision: 1,
    ...overrides,
  };
}

/** The signed-in reviewer holds `role`; Dana approves and Sam views. */
function serveTeam(role: Role) {
  const removed: string[] = [];
  server.use(
    http.get(`${API}/me`, () =>
      HttpResponse.json({ ...REVIEWER, memberships: [membership(role)] }),
    ),
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({ ...PROJECT, role, permissions: PERMISSIONS[role] }),
    ),
    http.get(MEMBERS_URL, () =>
      HttpResponse.json({
        members: [
          member({ role, waiting: role === 'approver' ? 3 : 0 }),
          member({
            user_id: DANA_ID,
            display_name: 'Dana Ruiz',
            job_title: 'Product owner',
            role: 'approver',
            joined_at: '2026-10-02T09:00:00Z',
            waiting: 3,
          }),
          member({ user_id: SAM_ID, display_name: 'Sam Okafor', role: 'viewer', waiting: 0 }),
        ],
      }),
    ),
    http.get(`${API}/projects/${PROJECT_ID}/invitations`, () =>
      HttpResponse.json({ invitations: [] }),
    ),
    http.delete(`${MEMBERS_URL}/:userId`, ({ params }) => {
      removed.push(String(params.userId));
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return removed;
}

function main() {
  return within(screen.getByRole('main'));
}

async function members() {
  return within(await main().findByRole('list', { name: 'Members' }));
}

function row(list: { getByText: (text: string) => HTMLElement }, name: string) {
  const item = list.getByText(name).closest('li');
  if (!item) {
    throw new Error(`No row for ${name}`);
  }
  return within(item);
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Team page', () => {
  it('is in the project menu and lists everyone with their role, what it allows, when they joined and what waits', async () => {
    serveTeam('approver');
    renderApp(PAGE);

    expect(await main().findByRole('heading', { level: 2, name: 'Team' })).toBeInTheDocument();
    expect(
      within(screen.getByRole('navigation', { name: 'Project' })).getByRole('link', {
        name: 'Team',
      }),
    ).toHaveAttribute('aria-current', 'page');
    const list = await members();
    const dana = row(list, 'Dana Ruiz');
    expect(dana.getByText('Product owner')).toBeInTheDocument();
    expect(dana.getByText('Approver')).toBeInTheDocument();
    expect(dana.getByText('waiting')).toHaveTextContent('3 waiting');
    expect(dana.getByText(/plus approve scope and manage the team\. Joined/)).toBeInTheDocument();
    expect(dana.getByRole('time')).toHaveAttribute('datetime', '2026-10-02T09:00:00Z');
    const sam = row(list, 'Sam Okafor');
    expect(sam.getByText('Nothing waiting')).toBeInTheDocument();
    expect(sam.getByText(/Can read everything and join discussions\./)).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('lets an Approver invite people, change roles and remove members', async () => {
    const removed = serveTeam('approver');
    renderApp(PAGE);

    const list = await members();
    expect(main().getByRole('button', { name: 'Invite people' })).toBeInTheDocument();
    expect(list.getByRole('button', { name: 'Change the role of Sam Okafor' })).toBeInTheDocument();
    await userEvent.click(list.getByRole('button', { name: 'Remove Sam Okafor' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Remove Sam Okafor?' }));
    await userEvent.click(dialog.getByRole('button', { name: 'Remove' }));

    await waitFor(() => {
      expect(removed).toEqual([SAM_ID]);
    });
  });

  it.each<Role>(['viewer', 'editor'])(
    'shows a %s the team without invite, role or remove actions',
    async (role) => {
      serveTeam(role);
      renderApp(PAGE);

      const list = await members();
      expect(list.getAllByRole('listitem')).toHaveLength(3);
      expect(main().queryByRole('button', { name: 'Invite people' })).not.toBeInTheDocument();
      expect(list.queryByRole('button', { name: /Change the role/ })).not.toBeInTheDocument();
      expect(list.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument();
      expect(
        main().getByText(/Only an Approver can invite people or change roles\./),
      ).toBeInTheDocument();
      // Anyone may still leave.
      expect(
        row(list, REVIEWER.display_name).getByRole('button', { name: 'Leave project' }),
      ).toBeInTheDocument();
    },
  );

  it('says when the team could not be loaded and tries again', async () => {
    serveTeam('viewer');
    let fail = true;
    server.use(
      http.get(MEMBERS_URL, () =>
        fail
          ? HttpResponse.json(
              {
                code: 'INTERNAL',
                message: 'Something went wrong',
                retryable: false,
                details: {},
                request_id: 'r',
              },
              { status: 500 },
            )
          : HttpResponse.json({ members: [member({ role: 'viewer' })] }),
      ),
    );
    renderApp(PAGE);

    const alert = await main().findByRole('alert');
    expect(alert).toHaveTextContent('Could not load the members. Something went wrong');
    fail = false;
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await members()).toBeTruthy();
  });
});
