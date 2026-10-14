import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';

import { server } from '@/test/server';

import { ActivityView } from './ActivityView';
import type { ActivityEvent } from './types';

const PROJECT_ID = '019a3a5e-0000-7000-8000-000000000001';
const ACTIVITY_URL = `*/api/v1/projects/${PROJECT_ID}/activity`;

function event(id: string, overrides: Partial<ActivityEvent>): ActivityEvent {
  return {
    id: `019a3a5e-0000-7000-8000-0000000001${id}`,
    project_id: PROJECT_ID,
    type: 'source.added',
    actor: {
      kind: 'user',
      user_id: '019a3a5e-0000-7000-8000-000000000002',
      display_name: 'Local Reviewer',
    },
    subjects: [],
    summary: 'Added brief.md',
    occurred_at: '2026-10-13T09:00:00Z',
    ...overrides,
  };
}

const ANSWERED = event('03', {
  type: 'clarification.answered',
  summary: 'Answered a question',
  occurred_at: '2026-10-13T11:00:00Z',
});
const DRAFTED = event('02', {
  type: 'backlog.draft_saved',
  actor: { kind: 'agent', user_id: null, display_name: null },
  summary: 'Saved draft backlog v1',
  occurred_at: '2026-10-13T10:00:00Z',
});
const ADDED = event('01', {});

function renderView() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ActivityView projectId={PROJECT_ID} />
    </QueryClientProvider>,
  );
}

function rows() {
  return within(screen.getByRole('list', { name: 'Activity' })).getAllByRole('listitem');
}

describe('ActivityView', () => {
  it('lists entries in the order the server returns, with when, who and what', async () => {
    server.use(
      http.get(ACTIVITY_URL, () =>
        HttpResponse.json({ events: [ANSWERED, DRAFTED, ADDED], next_cursor: null }),
      ),
    );

    renderView();

    await screen.findByRole('list', { name: 'Activity' });
    expect(rows().map((row) => row.textContent)).toEqual([
      expect.stringContaining('Local ReviewerAnswered a question'),
      expect.stringContaining('AgentSaved draft backlog v1'),
      expect.stringContaining('Local ReviewerAdded brief.md'),
    ]);
    expect(rows().map((row) => row.querySelector('time')?.getAttribute('datetime'))).toEqual([
      ANSWERED.occurred_at,
      DRAFTED.occurred_at,
      ADDED.occurred_at,
    ]);
    expect(screen.queryByRole('button', { name: 'Show older activity' })).not.toBeInTheDocument();
  });

  it('loads older entries on demand with the cursor the server returned', async () => {
    const cursors: (string | null)[] = [];
    server.use(
      http.get(ACTIVITY_URL, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor');
        cursors.push(cursor);
        return cursor === null
          ? HttpResponse.json({ events: [ANSWERED, DRAFTED], next_cursor: 'page-2' })
          : HttpResponse.json({ events: [ADDED], next_cursor: null });
      }),
    );
    renderView();
    await screen.findByRole('list', { name: 'Activity' });
    expect(rows()).toHaveLength(2);

    await userEvent.click(screen.getByRole('button', { name: 'Show older activity' }));

    await screen.findByText('Added brief.md');
    expect(rows()).toHaveLength(3);
    expect(cursors).toEqual([null, 'page-2']);
    expect(screen.queryByRole('button', { name: 'Show older activity' })).not.toBeInTheDocument();
  });

  it('says what will appear when the project has no activity', async () => {
    server.use(http.get(ACTIVITY_URL, () => HttpResponse.json({ events: [], next_cursor: null })));

    renderView();

    expect(await screen.findByRole('heading', { name: 'No activity yet' })).toBeInTheDocument();
  });

  it('shows the server error and recovers on retry', async () => {
    let failing = true;
    server.use(
      http.get(ACTIVITY_URL, () =>
        failing
          ? HttpResponse.json(
              {
                code: 'SERVICE_UNAVAILABLE',
                message: 'The database is unavailable',
                request_id: 'req-1',
                retryable: true,
                details: {},
              },
              { status: 503 },
            )
          : HttpResponse.json({ events: [ADDED], next_cursor: null }),
      ),
    );
    renderView();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load the activity log.');
    failing = false;
    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(await screen.findByText('Added brief.md')).toBeInTheDocument();
  });
});
