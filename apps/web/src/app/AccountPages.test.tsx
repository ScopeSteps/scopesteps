import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT_ID, REVIEWER } from '@/test/fixtures';
import { API } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { mockSession, PASSPHRASE } from '@/test/session';

const CHECK = { message: 'Check your email. If the address can be used, we sent it a link.' };
const TOKEN = 'a-synthetic-link-token-for-tests-only';
const NEW_USER = { ...REVIEWER, email: 'new.person@example.test', memberships: [] };

function record(method: 'post' | 'get', path: string, respond: () => Response) {
  const bodies: unknown[] = [];
  server.use(
    http[method](`${API}${path}`, async ({ request }) => {
      bodies.push(method === 'post' ? await request.json().catch(() => null) : null);
      return respond();
    }),
  );
  return bodies;
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('Creating an account', () => {
  it.each(['new.person@example.test', 'editor@scopesteps.local'])(
    'says "Check your email" the same way for %s and sends the link again on request',
    async (email) => {
      mockSession();
      const sent = record('post', '/auth/sign-up', () => HttpResponse.json(CHECK, { status: 202 }));
      const resent = record('post', '/auth/resend-verification', () =>
        HttpResponse.json(CHECK, { status: 202 }),
      );
      renderApp('/sign-in');
      await userEvent.click(await screen.findByRole('link', { name: 'Create an account' }));

      await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'New Person');
      await userEvent.type(screen.getByRole('textbox', { name: 'Email' }), email);
      await userEvent.type(screen.getByLabelText('Password'), PASSPHRASE);
      await userEvent.click(screen.getByRole('button', { name: 'Create account' }));

      expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeVisible();
      expect(screen.getByText(email)).toBeVisible();
      await userEvent.click(screen.getByRole('button', { name: 'Send the link again' }));
      expect(await screen.findByText('Sent again.')).toBeVisible();
      expect(sent).toEqual([{ display_name: 'New Person', email, password: PASSPHRASE }]);
      expect(resent).toEqual([{ email }]);
      await expectNoAccessibilityViolations();
    },
  );

  it("shows the server's reason for a weak password next to the password", async () => {
    mockSession();
    record('post', '/auth/sign-up', () =>
      HttpResponse.json(
        {
          ...errorBody('INVALID_INPUT', 'A password must be 12 to 1024 characters long'),
          details: { min_length: 12, max_length: 1024 },
        },
        { status: 422 },
      ),
    );
    renderApp('/sign-up');

    await userEvent.type(await screen.findByRole('textbox', { name: 'Name' }), 'New Person');
    await userEvent.type(screen.getByRole('textbox', { name: 'Email' }), 'a@example.test');
    await userEvent.type(screen.getByLabelText('Password'), 'short');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('12 to 1024 characters');
    expect(screen.getByLabelText('Password')).toHaveFocus();
  });

  it('confirms the email from the link, signs in and opens the home page', async () => {
    mockSession();
    const verified = record('post', '/auth/verify-email', () => HttpResponse.json(NEW_USER));
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(NEW_USER)),
      http.get(`${API}/projects`, () => HttpResponse.json({ projects: [] })),
    );

    const router = renderApp(`/verify-email/${TOKEN}`);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
    expect(verified).toEqual([{ token: TOKEN }]);
  });

  it('says an expired link no longer works and sends a new one', async () => {
    mockSession();
    record('post', '/auth/verify-email', () =>
      HttpResponse.json(errorBody('TOKEN_INVALID', 'This link is not valid any more.'), {
        status: 404,
      }),
    );
    const resent = record('post', '/auth/resend-verification', () =>
      HttpResponse.json(CHECK, { status: 202 }),
    );
    renderApp(`/verify-email/${TOKEN}`);

    expect(await screen.findByRole('alert')).toHaveTextContent('This link is not valid any more.');
    await userEvent.type(screen.getByRole('textbox', { name: 'Email' }), 'a@example.test');
    await userEvent.click(screen.getByRole('button', { name: 'Send a new link' }));

    expect(await screen.findByRole('heading', { name: 'Check your email' })).toBeVisible();
    expect(resent).toEqual([{ email: 'a@example.test' }]);
  });

  it('explains an unconfirmed sign-in and offers a new link', async () => {
    mockSession();
    record('post', '/auth/sign-in', () =>
      HttpResponse.json(errorBody('EMAIL_NOT_VERIFIED', 'Confirm your email address first.'), {
        status: 403,
      }),
    );
    const resent = record('post', '/auth/resend-verification', () =>
      HttpResponse.json(CHECK, { status: 202 }),
    );
    renderApp('/sign-in');

    await userEvent.type(await screen.findByRole('textbox', { name: 'Email' }), 'a@example.test');
    await userEvent.type(screen.getByLabelText('Password'), PASSPHRASE);
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Send the link again' }));

    expect(screen.getAllByRole('alert')[0]).toHaveTextContent('Confirm your email address first.');
    expect(await screen.findByText('Sent. Check your email.')).toBeVisible();
    expect(resent).toEqual([{ email: 'a@example.test' }]);
  });
});

const OFFER = {
  project_id: PROJECT_ID,
  project_name: 'Study Room Booking',
  invited_by_name: 'Ann Approver',
  email: 'new.person@example.test',
  roles: ['viewer', 'editor'],
  expires_at: '2026-11-03T09:00:00Z',
  has_account: false,
};

function offer(overrides: Partial<typeof OFFER> = {}) {
  server.use(
    http.get(`${API}/invitations/${TOKEN}`, () => HttpResponse.json({ ...OFFER, ...overrides })),
  );
}

describe('Opening an invitation', () => {
  it('lets the invited, signed-in person join and opens the project', async () => {
    mockSession({ signedIn: true });
    server.use(http.get(`${API}/me`, () => HttpResponse.json(NEW_USER)));
    offer({ has_account: true });
    const accepted = record('post', `/invitations/${TOKEN}/accept`, () =>
      HttpResponse.json({ project_id: PROJECT_ID, user: NEW_USER }),
    );
    const router = renderApp(`/invite/${TOKEN}`);

    expect(
      await screen.findByRole('heading', {
        name: 'Ann Approver invited you to Study Room Booking',
      }),
    ).toBeVisible();
    expect(screen.getByText('Viewer and Editor')).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Join the project' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/chat`);
    });
    expect(accepted).toHaveLength(1);
  });

  it('sends a signed-out person with an account to sign in first, then back here', async () => {
    mockSession();
    offer({ has_account: true });
    renderApp(`/invite/${TOKEN}`);

    const link = await screen.findByRole('link', { name: 'Sign in to join' });
    const target = new URL(link.getAttribute('href') ?? '', 'https://app.test');

    expect(target.pathname).toBe('/sign-in');
    expect(target.searchParams.get('email')).toBe(OFFER.email);
    expect(target.searchParams.get('next')).toBe(`/invite/${TOKEN}`);
  });

  it('prefills the email when signing in from an invitation', async () => {
    mockSession();
    renderApp(`/sign-in?email=${encodeURIComponent(OFFER.email)}&next=/invite/${TOKEN}`);

    expect(await screen.findByRole('textbox', { name: 'Email' })).toHaveValue(OFFER.email);
  });

  it('creates the account of someone new and lands them in the project, signed in', async () => {
    mockSession();
    offer();
    const created = record('post', `/invitations/${TOKEN}/sign-up`, () =>
      HttpResponse.json({ project_id: PROJECT_ID, user: NEW_USER }),
    );
    const router = renderApp(`/invite/${TOKEN}`);

    expect(await screen.findByRole('heading', { name: 'Create your account' })).toBeVisible();
    const email = screen.getByRole('textbox', { name: 'Email' });
    expect(email).toHaveValue(OFFER.email);
    expect(email).toHaveAttribute('readonly');
    await userEvent.type(screen.getByRole('textbox', { name: 'Name' }), 'New Person');
    await userEvent.type(screen.getByLabelText('Password'), PASSPHRASE);
    await userEvent.click(screen.getByRole('button', { name: 'Create account and join' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/chat`);
    });
    expect(created).toEqual([{ display_name: 'New Person', password: PASSPHRASE }]);
    await expectNoAccessibilityViolations();
  });

  it('asks someone signed in with another email to switch accounts', async () => {
    const session = mockSession({ signedIn: true });
    offer({ has_account: true });
    const router = renderApp(`/invite/${TOKEN}`);

    expect(await screen.findByText(REVIEWER.email)).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out and sign in' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/sign-in');
    });
    expect(session.signOuts).toBe(1);
    expect(new URLSearchParams(router.state.location.search).get('email')).toBe(OFFER.email);
  });

  it('says plainly that an invalid link no longer works', async () => {
    mockSession();
    server.use(
      http.get(`${API}/invitations/${TOKEN}`, () =>
        HttpResponse.json(
          errorBody(
            'INVITATION_INVALID',
            'This invitation is not valid any more. Ask the person who invited you for a new one.',
          ),
          { status: 404 },
        ),
      ),
    );
    renderApp(`/invite/${TOKEN}`);

    expect(
      await screen.findByRole('heading', { name: 'This invitation no longer works' }),
    ).toBeVisible();
    expect(screen.getByRole('alert')).toHaveTextContent('Ask the person who invited you');
  });
});
