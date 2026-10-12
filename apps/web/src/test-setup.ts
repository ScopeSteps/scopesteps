import '@testing-library/jest-dom/vitest';
import { afterAll, afterEach } from 'vitest';

import { server } from '@/test/server';

// Listen before test modules load: API clients capture `fetch` at import time.
server.listen({ onUnhandledFrame: 'error' });

afterEach(() => {
  server.resetHandlers();
});
afterAll(() => {
  server.close();
});
