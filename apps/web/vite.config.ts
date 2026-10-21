import { fileURLToPath } from 'node:url';

import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

import { BalancedSequencer } from './src/test/balancedSequencer';

// The end-to-end tests run their own API on another port (e2e/playwright.config.ts).
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    proxy: {
      '/api': apiTarget,
      '/health': apiTarget,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    // Whole-page tests render the real routes in jsdom; on a slower laptop running the dev
    // servers, a full parallel run takes several times as long as CI, so 5 s was not enough.
    testTimeout: 20_000,
    sequence: { sequencer: BalancedSequencer },
  },
});
