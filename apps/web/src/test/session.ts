import { http, HttpResponse } from 'msw';

import { errorBody, REVIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { server } from '@/test/server';

/** The one password the mocked server accepts. Synthetic, like every fixture. */
export const PASSPHRASE = 'synthetic passphrase for tests';

export interface MockSession {
  signedIn: boolean;
  /** Every body sent to sign-in, in order. */
  signIns: unknown[];
  signOuts: number;
}

function isCredentials(body: unknown): body is { email: string; password: string } {
  return (
    typeof body === 'object' &&
    body !== null &&
    'email' in body &&
    typeof body.email === 'string' &&
    'password' in body &&
    typeof body.password === 'string'
  );
}

/**
 * A server with session sign-in over `projectHandlers()`: sign-in with `PASSPHRASE` starts the
 * session, sign-out ends it, and without one every other API route answers 401 as the API does.
 * Set `signedIn` to false to end the session behind the page's back.
 */
export function mockSession({ signedIn = false } = {}): MockSession {
  const session: MockSession = { signedIn, signIns: [], signOuts: 0 };
  server.use(
    http.post(`${API}/auth/sign-in`, async ({ request }) => {
      const body = await request.json();
      session.signIns.push(body);
      if (!isCredentials(body) || body.password !== PASSPHRASE) {
        return HttpResponse.json(
          errorBody('INVALID_CREDENTIALS', 'Email or password is incorrect'),
          { status: 401 },
        );
      }
      session.signedIn = true;
      return HttpResponse.json(REVIEWER);
    }),
    http.post(`${API}/auth/sign-out`, () => {
      session.signOuts += 1;
      session.signedIn = false;
      return new HttpResponse(null, { status: 204 });
    }),
    http.all(`${API}/*`, () =>
      session.signedIn
        ? undefined
        : HttpResponse.json(errorBody('UNAUTHENTICATED', 'Sign in to continue'), {
            status: 401,
          }),
    ),
    ...projectHandlers(),
  );
  return session;
}
