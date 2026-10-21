import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { API, projectHandlers } from '@/test/handlers';
import { PROJECT_ID } from '@/test/fixtures';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const REPLAY = { provider: 'replay', model_id: 'gemini-3.5-flash-lite', replay: true };

describe('ReplayBanner', () => {
  it('says on every page that the agent is a replay when the API serves one', async () => {
    server.use(
      ...projectHandlers(),
      http.get(`${API}/agent/model`, () => HttpResponse.json(REPLAY)),
    );

    renderApp(`/projects/${PROJECT_ID}/sources`);

    const banner = await screen.findByText('Replay, not a live agent.');
    expect(banner.closest('[role="status"]')).toHaveTextContent(
      'replayed from a recorded run of gemini-3.5-flash-lite',
    );
    await expectNoAccessibilityViolations();
  });

  it('shows nothing for a live model', async () => {
    server.use(...projectHandlers());

    renderApp(`/projects/${PROJECT_ID}/sources`);

    expect(await screen.findByRole('table', { name: 'Stored sources' })).toBeInTheDocument();
    expect(screen.queryByText(/Replay, not a live agent/)).not.toBeInTheDocument();
  });
});
