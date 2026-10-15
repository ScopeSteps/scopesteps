import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { BRIEF, errorBody, PROJECT_ID, REVIEWER } from '@/test/fixtures';
import { API } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { mockSession, PASSPHRASE } from '@/test/session';

const SOURCES_URL = `/projects/${PROJECT_ID}/sources`;
const ACTIVITY_URL = `/projects/${PROJECT_ID}/activity`;

async function signIn() {
  await userEvent.type(await screen.findByRole('textbox', { name: 'Email' }), REVIEWER.email);
  await userEvent.type(screen.getByLabelText('Password'), PASSPHRASE);
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

function accountButton() {
  return screen.findByRole('button', { name: /Local Reviewer/ });
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}/activity`, () =>
      HttpResponse.json({ events: [], next_cursor: null }),
    ),
  );
});

describe('SessionGuard', () => {
  it('sends a signed-out visitor to sign-in and back to the page they asked for', async () => {
    mockSession();
    const deepLink = `${SOURCES_URL}?source=${BRIEF.id}#top`;
    const router = renderApp(deepLink);

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/sign-in');
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe(deepLink);
    expect(screen.queryByText(/session has ended/)).not.toBeInTheDocument();

    await signIn();

    await waitFor(() => {
      expect(
        `${router.state.location.pathname}${router.state.location.search}${router.state.location.hash}`,
      ).toBe(deepLink);
    });
    expect(await screen.findAllByText(BRIEF.filename)).not.toHaveLength(0);
  });

  it('returns to sign-in when the session ends, keeps the page and asks again from scratch', async () => {
    const session = mockSession({ signedIn: true });
    const router = renderApp(SOURCES_URL);
    expect(await screen.findAllByText(BRIEF.filename)).not.toHaveLength(0);

    session.signedIn = false;
    await userEvent.click(screen.getByRole('link', { name: 'Activity' }));

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(
      screen.getByText('Your session has ended. Sign in again to continue.'),
    ).toBeInTheDocument();
    expect(new URLSearchParams(router.state.location.search).get('next')).toBe(ACTIVITY_URL);

    await signIn();

    await waitFor(() => {
      expect(router.state.location.pathname).toBe(ACTIVITY_URL);
    });
    expect(await accountButton()).toBeInTheDocument();
  });

  it('signs out from the account menu by keyboard, and Back shows none of the old data', async () => {
    const session = mockSession({ signedIn: true });
    const router = renderApp(SOURCES_URL);
    expect(await screen.findAllByText(BRIEF.filename)).not.toHaveLength(0);
    await userEvent.click(screen.getByRole('link', { name: 'Activity' }));
    await screen.findByRole('heading', { name: 'Activity' });

    (await accountButton()).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('menuitem', { name: 'Sign out' })).toHaveFocus();
    await userEvent.keyboard('{Enter}');

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(session.signOuts).toBe(1);
    expect(router.state.location.search).toBe('');
    expect(screen.queryByText(/session has ended/)).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Email' })).toHaveFocus();

    let oldDataShown = false;
    const watcher = new MutationObserver(() => {
      oldDataShown ||= document.body.textContent.includes(BRIEF.filename);
    });
    watcher.observe(document.body, { childList: true, subtree: true, characterData: true });

    await router.navigate(-1);

    expect(router.state.location.pathname).toBe(SOURCES_URL);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/sign-in');
    });
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    watcher.disconnect();
    expect(oldDataShown).toBe(false);
  });

  it('signs out from the Account section of the settings', async () => {
    const session = mockSession({ signedIn: true });
    renderApp(SOURCES_URL);
    await userEvent.click(await accountButton());
    await userEvent.click(screen.getByRole('menuitem', { name: 'Settings' }));
    await userEvent.click(
      within(screen.getByRole('navigation', { name: 'Settings sections' })).getByRole('button', {
        name: 'Account',
      }),
    );

    const email = screen.getByRole('textbox', { name: 'Email' });
    expect(email).toHaveValue(REVIEWER.email);
    expect(email).toHaveAttribute('readonly');
    await expectNoAccessibilityViolations();

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(session.signOuts).toBe(1);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('stays signed in and says so when sign-out fails', async () => {
    mockSession({ signedIn: true });
    server.use(
      http.post(`${API}/auth/sign-out`, () =>
        HttpResponse.json(errorBody('UNAVAILABLE', 'Try again shortly.', true), { status: 503 }),
      ),
    );
    const router = renderApp(SOURCES_URL);
    await userEvent.click(await accountButton());

    await userEvent.click(screen.getByRole('menuitem', { name: 'Sign out' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not sign out. Try again shortly.',
    );
    expect(router.state.location.pathname).toBe(SOURCES_URL);
  });
});
