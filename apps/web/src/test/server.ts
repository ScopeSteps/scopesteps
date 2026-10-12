import { setupServer } from 'msw/node';

/** Network mock for tests. Add per-test handlers with `server.use(...)`. */
export const server = setupServer();
