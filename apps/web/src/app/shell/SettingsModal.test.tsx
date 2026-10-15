import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import type { components } from '@scopesteps/api-client';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { APPROVER, errorBody, PROJECT_ID, REVIEWER, VIEWER } from '@/test/fixtures';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type CurrentUser = components['schemas']['CurrentUserResponse'];
type UpdateProfileRequest = components['schemas']['UpdateProfileRequest'];

const SOURCES_URL = `/projects/${PROJECT_ID}/sources`;

function useUser(user: CurrentUser) {
  server.use(http.get('*/api/v1/me', () => HttpResponse.json(user)));
}

async function openSettings(name: string, tab: 'Profile' | 'Account') {
  await userEvent.click(await screen.findByRole('button', { name: new RegExp(name) }));
  await userEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));
  await userEvent.click(
    within(screen.getByRole('navigation', { name: 'Settings sections' })).getByRole('button', {
      name: tab,
    }),
  );
  return screen.getByRole('dialog', { name: 'Your settings' });
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  useUser(REVIEWER);
});

describe('Profile settings', () => {
  it('saves the name, job title and about text with the revision it was opened on', async () => {
    const sent: UpdateProfileRequest[] = [];
    server.use(
      http.patch('*/api/v1/me', async ({ request }) => {
        const body = (await request.json()) as UpdateProfileRequest;
        sent.push(body);
        return HttpResponse.json({
          ...REVIEWER,
          display_name: body.display_name,
          job_title: body.job_title,
          about: body.about,
          revision: 2,
        });
      }),
    );
    renderApp(SOURCES_URL);
    const dialog = await openSettings('Local Reviewer', 'Profile');

    const name = within(dialog).getByRole('textbox', { name: 'Full name' });
    await userEvent.clear(name);
    await userEvent.type(name, 'Priya Shah');
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Job title' }), 'Analyst');
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'About you' }), 'Hello');
    expect(within(dialog).getByText('5 / 280')).toBeInTheDocument();
    await expectNoAccessibilityViolations();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Save profile' }));

    expect(await screen.findByText('Profile saved.')).toBeInTheDocument();
    expect(sent).toEqual([
      { display_name: 'Priya Shah', job_title: 'Analyst', about: 'Hello', expected_revision: 1 },
    ]);
    // The account button names the user by the saved profile; nothing is kept in the browser.
    expect(await screen.findByRole('button', { name: /Priya Shah/ })).toBeInTheDocument();
    expect(Object.keys(window.localStorage)).not.toContainEqual(expect.stringMatching(/profile/i));
    expect(JSON.stringify(window.localStorage)).not.toContain('Priya Shah');
    expect(window.sessionStorage).toHaveLength(0);
  });

  it('asks for a name before saving and shows the field the server refuses', async () => {
    let calls = 0;
    server.use(
      http.patch('*/api/v1/me', () => {
        calls += 1;
        return HttpResponse.json(
          {
            ...errorBody('PROFILE_INVALID', 'A job title can have at most 80 characters.'),
            details: { field: 'job_title', max_chars: 80 },
          },
          { status: 422 },
        );
      }),
    );
    renderApp(SOURCES_URL);
    const dialog = await openSettings('Local Reviewer', 'Profile');

    const name = within(dialog).getByRole('textbox', { name: 'Full name' });
    await userEvent.clear(name);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save profile' }));

    expect(name).toHaveAccessibleDescription('Enter your name.');
    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(calls).toBe(0);

    await userEvent.type(name, 'Local Reviewer');
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Job title' }), 'Lead');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save profile' }));

    const title = within(dialog).getByRole('textbox', { name: 'Job title' });
    await waitFor(() => {
      expect(title).toHaveAccessibleDescription('A job title can have at most 80 characters.');
    });
    expect(title).toHaveAttribute('aria-invalid', 'true');
    expect(calls).toBe(1);
    await expectNoAccessibilityViolations();
  });

  it('asks for a reload instead of saving over a newer profile', async () => {
    server.use(
      http.patch('*/api/v1/me', () =>
        HttpResponse.json(
          errorBody('PROFILE_CHANGED', 'Your profile changed. Reload it and try again.'),
          { status: 409 },
        ),
      ),
    );
    renderApp(SOURCES_URL);
    const dialog = await openSettings('Local Reviewer', 'Profile');
    await userEvent.type(within(dialog).getByRole('textbox', { name: 'Job title' }), 'Lead');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save profile' }));

    const banner = await within(dialog).findByRole('alert');
    expect(banner).toHaveTextContent('Your profile changed somewhere else');
    expect(within(dialog).getByRole('button', { name: 'Save profile' })).toBeDisabled();

    useUser({ ...REVIEWER, job_title: 'Facilitator', revision: 3 });
    await userEvent.click(within(banner).getByRole('button', { name: 'Reload' }));

    await waitFor(() => {
      expect(within(dialog).getByRole('textbox', { name: 'Job title' })).toHaveValue('Facilitator');
    });
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Save profile' })).toBeEnabled();
  });
});

describe('Account settings', () => {
  it.each([
    {
      user: REVIEWER,
      label: 'Business analyst',
      allows: 'Add and remove sources',
      refuses: 'Can’t approve or reject versions',
    },
    {
      user: APPROVER,
      label: 'Product owner',
      allows: 'Approve or reject versions',
      refuses: 'Can’t edit drafts, sources or people',
    },
    {
      user: VIEWER,
      label: 'Viewer',
      allows: 'Read the backlog, evidence and activity',
      refuses: 'Can’t make scope decisions',
    },
  ])(
    'shows the email and the $label role read-only, with what it allows',
    async ({ user, label, allows, refuses }) => {
      useUser(user);
      renderApp(SOURCES_URL);
      const dialog = await openSettings(user.display_name, 'Account');

      const email = within(dialog).getByRole('textbox', { name: 'Email' });
      expect(email).toHaveValue(user.email);
      expect(email).toHaveAttribute('readonly');
      const role = within(dialog).getByRole('region', { name: /Role in this project/ });
      expect(role).toHaveTextContent(label);
      const list = within(role).getByRole('list', { name: 'What your role allows' });
      expect(within(list).getByText(allows)).toBeInTheDocument();
      expect(within(list).getByText(refuses)).toBeInTheDocument();
      expect(within(dialog).getByRole('button', { name: 'Sign out' })).toBeInTheDocument();
      await expectNoAccessibilityViolations();
    },
  );
});
