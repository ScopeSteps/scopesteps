import type { paths } from '@scopesteps/api-client';
import createClient from 'openapi-fetch';

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL;

/**
 * Typed API client. Types are generated from contracts/openapi.json.
 * An unset or empty VITE_API_BASE_URL means same origin (the Vite dev proxy locally).
 */
export const api = createClient<paths>({
  baseUrl:
    configuredBaseUrl === undefined || configuredBaseUrl === ''
      ? window.location.origin
      : configuredBaseUrl,
});
