import { randomBytes } from 'node:crypto';
import { fileURLToPath } from 'node:url';

import { defineConfig, devices } from '@playwright/test';

/**
 * The critical flow runs against the real API and web app. By default the agent is a replay of
 * a recorded live run (`MODEL_PROVIDER=replay`), so no model is called and the app says it is a
 * replay. `E2E_MODE=record` runs the same flow on the live model from `.env` and records it.
 */
const mode = process.env.E2E_MODE === 'record' ? 'record' : 'replay';
const recording = fileURLToPath(new URL('./recordings/campus-room-booking.json', import.meta.url));
const apiPort = 8011;
const webPort = 5183;
const webUrl = `http://localhost:${String(webPort)}`;
// Each run seeds the accounts with a password nobody else knows; it never leaves this process.
export const password = process.env.E2E_PASSWORD ?? randomBytes(18).toString('base64url');
process.env.E2E_PASSWORD = password;

const model: Record<string, string> =
  mode === 'record'
    ? { MODEL_FALLBACK_PROVIDER: 'none', MODEL_RECORD_FILE: recording }
    : { MODEL_PROVIDER: 'replay', MODEL_FALLBACK_PROVIDER: 'none', MODEL_REPLAY_FILE: recording };

export default defineConfig({
  testDir: './tests',
  // One flow through one database: the steps depend on each other.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  // One test covers the whole flow: two to four minutes on a replay, longer in CI, and a live
  // recording also waits on the model at every step.
  timeout: mode === 'record' ? 15 * 60_000 : 10 * 60_000,
  expect: { timeout: mode === 'record' ? 120_000 : 15_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: webUrl,
    trace: 'retain-on-failure',
    // A click that cannot happen fails with its own message instead of using up the test.
    actionTimeout: 45_000,
    video: process.env.E2E_VIDEO === 'on' ? 'on' : 'retain-on-failure',
    // E2E_SLOWMO=500 slows each action down, for a video people can follow.
    launchOptions: { slowMo: Number(process.env.E2E_SLOWMO ?? 0) },
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: [
    {
      command: './scripts/start-api.sh',
      url: `http://127.0.0.1:${String(apiPort)}/health/ready`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        // test, not local: the API then runs without reload, so a file saved mid-run cannot restart it.
        APP_ENV: 'test',
        API_HOST: '127.0.0.1',
        API_PORT: String(apiPort),
        DATABASE_URL: 'sqlite:///var/e2e.db',
        CORS_ALLOWED_ORIGINS: webUrl,
        AUTH_MODE: 'session',
        SEED_ACCOUNT_PASSWORD: password,
        ...model,
      },
    },
    {
      command: `pnpm --filter @scopesteps/web exec vite --port ${String(webPort)} --strictPort`,
      url: webUrl,
      reuseExistingServer: false,
      timeout: 120_000,
      env: { API_PROXY_TARGET: `http://127.0.0.1:${String(apiPort)}` },
    },
  ],
});
