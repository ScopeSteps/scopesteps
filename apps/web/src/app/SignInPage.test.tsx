import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, REVIEWER } from '@/test/fixtures';
import { API } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { mockSession, PASSPHRASE } from '@/test/session';

function emailField() {
  return screen.getByRole('textbox', { name: 'Email' });
}

// A password input has no ARIA role, so it is found by its label.
function passwordField() {
  return screen.getByLabelText('Password');
}

function submitButton() {
  return screen.getByRole('button', { name: /^Sign(ing)? in/ });
}

async function signIn(email: string, password: string) {
  await userEvent.type(emailField(), email);
  await userEvent.type(passwordField(), password);
  await userEvent.click(submitButton());
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

describe('SignInPage', () => {
  it('labels its fields for password managers and puts focus in the email field', async () => {
    mockSession();
    renderApp('/sign-in');

    expect(await screen.findByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument();
    expect(emailField()).toHaveFocus();
    expect(emailField()).toHaveAttribute('type', 'email');
    expect(emailField()).toHaveAttribute('autocomplete', 'username');
    expect(passwordField()).toHaveAttribute('type', 'password');
    expect(passwordField()).toHaveAttribute('autocomplete', 'current-password');
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('signs in from the keyboard alone and opens the app', async () => {
    const session = mockSession();
    const router = renderApp('/sign-in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await userEvent.keyboard('Editor@Scopesteps.local ');
    await userEvent.tab();
    await userEvent.keyboard(PASSPHRASE);
    await userEvent.keyboard('{Enter}');

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
    expect(session.signIns).toEqual([{ email: 'Editor@Scopesteps.local', password: PASSPHRASE }]);
    // The home page lists the projects; the account menu appears once the session loads.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Local Reviewer/ })).toBeInTheDocument();
    });
  });

  it('checks the format only and sends nothing until both fields make sense', async () => {
    const session = mockSession();
    renderApp('/sign-in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await userEvent.type(emailField(), 'not-an-email');
    await userEvent.click(submitButton());

    expect(screen.getByRole('alert')).toHaveTextContent('Enter a valid email address.');
    expect(emailField()).toHaveFocus();
    expect(emailField()).toHaveAttribute('aria-invalid', 'true');
    expect(emailField()).toHaveAccessibleDescription('Enter a valid email address.');

    await userEvent.clear(emailField());
    await userEvent.type(emailField(), 'editor@scopesteps.local');
    await userEvent.click(submitButton());

    expect(screen.getByRole('alert')).toHaveTextContent('Enter your password.');
    expect(passwordField()).toHaveFocus();
    expect(passwordField()).toHaveAttribute('aria-invalid', 'true');
    expect(emailField()).not.toHaveAttribute('aria-invalid');
    expect(session.signIns).toEqual([]);
  });

  it.each([
    ['a wrong password', 'editor@scopesteps.local'],
    ['an unknown email', 'nobody@scopesteps.local'],
  ])('says the same for %s, clears the password and stays on sign-in', async (_case, email) => {
    mockSession();
    const router = renderApp('/sign-in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await signIn(email, 'a wrong passphrase');

    expect(await screen.findByRole('alert')).toHaveTextContent(/^Email or password is incorrect$/);
    expect(passwordField()).toHaveFocus();
    expect(passwordField()).toHaveValue('');
    expect(passwordField()).toHaveAccessibleDescription('Email or password is incorrect');
    expect(emailField()).toHaveValue(email);
    expect(router.state.location.pathname).toBe('/sign-in');
    expect(screen.queryByText(/session has ended/)).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it("shows the server's reason when sign-in is not available", async () => {
    server.use(
      http.post(`${API}/auth/sign-in`, () =>
        HttpResponse.json(errorBody('SIGN_IN_DISABLED', 'Sign-in is not enabled on this server'), {
          status: 503,
        }),
      ),
    );
    renderApp('/sign-in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await signIn('editor@scopesteps.local', PASSPHRASE);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Sign-in is not enabled on this server',
    );
    expect(passwordField()).toHaveValue(PASSPHRASE);
  });

  it('shows that it is signing in and ignores another submit meanwhile', async () => {
    let requests = 0;
    server.use(
      http.post(`${API}/auth/sign-in`, async () => {
        requests += 1;
        await delay('infinite');
        return HttpResponse.json(REVIEWER);
      }),
    );
    renderApp('/sign-in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await signIn('editor@scopesteps.local', PASSPHRASE);

    const pending = await screen.findByRole('button', { name: 'Signing in…' });
    expect(pending).toHaveAttribute('aria-disabled', 'true');
    expect(pending).toHaveFocus();
    await userEvent.click(pending);
    await userEvent.type(passwordField(), '{Enter}');
    expect(requests).toBe(1);
  });

  it('shows and hides the password on request', async () => {
    mockSession();
    renderApp('/sign-in');
    await screen.findByRole('heading', { name: 'Sign in' });
    await userEvent.type(passwordField(), PASSPHRASE);

    await userEvent.click(screen.getByRole('button', { name: 'Show password' }));

    expect(passwordField()).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }));

    expect(passwordField()).toHaveAttribute('type', 'password');
  });

  it('never writes the password or the session to browser storage', async () => {
    mockSession();
    renderApp('/sign-in');
    await screen.findByRole('heading', { name: 'Sign in' });

    await signIn('editor@scopesteps.local', PASSPHRASE);
    await screen.findByRole('button', { name: /Local Reviewer/ });

    const stored = [window.localStorage, window.sessionStorage]
      .flatMap((storage) =>
        Array.from({ length: storage.length }, (_, index) => {
          const key = storage.key(index) ?? '';
          return `${key}=${storage.getItem(key) ?? ''}`;
        }),
      )
      .concat(document.cookie)
      .join('\n');
    expect(stored).not.toContain(PASSPHRASE);
    expect(stored).not.toMatch(/session/i);
    expect(window.sessionStorage).toHaveLength(0);
  });

  it('ignores a return address that leads off the app', async () => {
    mockSession();
    const router = renderApp(`/sign-in?next=${encodeURIComponent('//evil.example/steal')}`);
    await screen.findByRole('heading', { name: 'Sign in' });

    await signIn('editor@scopesteps.local', PASSPHRASE);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/');
    });
  });
});
