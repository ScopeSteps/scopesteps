import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

/**
 * Network mock for tests. Add per-test handlers with `server.use(...)`. The shell asks which
 * model the agent uses on every page; by default it is a live one.
 */
export const server = setupServer(
  http.get('*/api/v1/agent/model', () =>
    HttpResponse.json({ provider: 'gemini', model_id: 'gemini-3.5-flash-lite', replay: false }),
  ),
);
