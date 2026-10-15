import type { paths } from '@scopesteps/api-client';
import createClient from 'openapi-fetch';

import { reportSessionEnded } from './sessionEvents';

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;

// A wrong password is also a 401, but it only means the form should say so.
const SIGN_IN_PATH = '/api/v1/auth/sign-in';

/**
 * Typed API client. Types are generated from contracts/openapi.json.
 * An unset or empty VITE_API_BASE_URL means same origin (the Vite dev proxy locally).
 * The session cookie is HttpOnly and travels by itself; no script ever reads or stores it.
 */
export const api = createClient<paths>({
  baseUrl:
    configuredBaseUrl === undefined || configuredBaseUrl === ''
      ? window.location.origin
      : configuredBaseUrl,
});

api.use({
  onResponse({ request, response }) {
    if (response.status === 401 && !new URL(request.url).pathname.endsWith(SIGN_IN_PATH)) {
      reportSessionEnded();
    }
  },
});
