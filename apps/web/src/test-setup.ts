import { File as NodeFile } from 'node:buffer';

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, vi } from 'vitest';

import { server } from '@/test/server';

// The mocked network is Node's fetch, which can neither send nor parse jsdom's FormData and
// File, so tests use Node's. Node does not export its FormData class; take it from a response.
vi.stubGlobal('File', NodeFile);
vi.stubGlobal('FormData', (await new Response(new URLSearchParams()).formData()).constructor);

// Listen before test modules load: API clients capture `fetch` at import time.
server.listen({ onUnhandledFrame: 'error' });

afterEach(() => {
  // Testing Library only unmounts by itself when Vitest globals are enabled; they are not.
  cleanup();
  server.resetHandlers();
});
afterAll(() => {
  server.close();
});
