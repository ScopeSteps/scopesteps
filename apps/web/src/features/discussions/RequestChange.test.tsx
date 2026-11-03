import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { changeRequest } from '@/test/changeFixtures';
import {
  APPROVER,
  BACKLOG,
  errorBody,
  makeRun,
  PROJECT,
  PROJECT_ID,
  REVIEWER_ID,
  VIEWER,
} from '@/test/fixtures';
import { API, CHANGE_REQUESTS_URL, MESSAGES_URL, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Thread = components['schemas']['ThreadResponse'];

const NOW = '2026-10-30T09:00:00Z';
const THREAD_ID = '019a3a5e-0000-7000-8000-0000000000b1';
const CR_ID = '019a3a5e-0000-7000-8000-0000000000b5';
const DISCUSSION = `/projects/${PROJECT_ID}/discussion`;
const CHAT = `/projects/${PROJECT_ID}/chat?discussion=${THREAD_ID}`;
const QUOTE = 'Sam Okafor, 2026-10-29: Societies keep asking for weekly bookings.';
const PROJECT_WITH_BASELINE = {
  ...PROJECT,
  status: {
    ...PROJECT.status,
    state: 'baseline',
    baseline_version: 1,
    baseline_version_id: BACKLOG.id,
  },
};

function thread(overrides: Partial<Thread> = {}): Thread {
  return {
    id: THREAD_ID,
    project_id: PROJECT_ID,
    item_id: null,
    item: null,
    status: 'open',
    revision: 1,
    created_by: REVIEWER_ID,
    created_at: NOW,
    last_activity_at: NOW,
    resolved_at: null,
    resolved_by: null,
    resolved_by_name: null,
    comments: [
      {
        id: '019a3a5e-0000-7000-8000-0000000000b2',
        author_id: REVIEWER_ID,
        author_name: 'Sam Okafor',
        body: 'Societies keep asking for weekly bookings.',
        mentions: [],
        deleted: false,
        revision: 1,
        backlog_version_id: null,
        created_at: NOW,
        edited_at: null,
      },
    ],
    following: true,
    change_requests: [],
    ...overrides,
  };
}

function serveThreads(threads: Thread[]) {
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}/threads`, () =>
      HttpResponse.json({ threads, next_cursor: null }),
    ),
  );
}

function serveChat(shortened = false) {
  const sent: Record<string, unknown>[] = [];
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}`, () => HttpResponse.json(PROJECT_WITH_BASELINE)),
    http.get(`${API}/projects/${PROJECT_ID}/backlogs/${BACKLOG.id}`, () =>
      HttpResponse.json(BACKLOG),
    ),
    http.get(`${API}/threads/${THREAD_ID}/change-request-draft`, () =>
      HttpResponse.json({ text: QUOTE, shortened }),
    ),
    http.post(MESSAGES_URL, async ({ request }) => {
      sent.push((await request.json()) as Record<string, unknown>);
      return HttpResponse.json(
        {
          message: {
            id: '019a3a5e-0000-7000-8000-0000000000a1',
            project_id: PROJECT_ID,
            role: 'user',
            kind: 'change_request',
            text: 'x',
            created_at: NOW,
          },
          run: makeRun({ mode: 'change', status: 'created' }),
        },
        { status: 202 },
      );
    }),
    http.post(`${API}/runs/:id/advance`, () =>
      HttpResponse.json(makeRun({ mode: 'change', status: 'failed' })),
    ),
  );
  return sent;
}

beforeEach(() => {
  window.sessionStorage.clear();
  server.use(...projectHandlers());
});

describe('Request a change from this discussion', () => {
  it('is offered to editors and approvers', async () => {
    serveThreads([thread()]);
    server.use(http.get(`${API}/me`, () => HttpResponse.json(APPROVER)));

    renderApp(DISCUSSION);

    expect(
      await screen.findByRole('link', { name: 'Request a change from this discussion' }),
    ).toHaveAttribute('href', CHAT);
  });

  it('is not offered to viewers', async () => {
    serveThreads([thread()]);
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));

    renderApp(DISCUSSION);

    await screen.findByRole('button', { name: 'Following' });
    expect(
      screen.queryByRole('link', { name: 'Request a change from this discussion' }),
    ).not.toBeInTheDocument();
  });

  it('opens the change request box with the quote, the cursor on the first line', async () => {
    serveChat();

    renderApp(CHAT);

    const box = await screen.findByRole('textbox', { name: /What should change/ });
    await waitFor(() => {
      expect(box).toHaveValue(`\n\n${QUOTE}`);
    });
    expect(box).toHaveFocus();
    expect((box as HTMLTextAreaElement).selectionStart).toBe(0);
    expect(screen.getByText(/From a discussion/)).toBeVisible();
  });

  it('says when older comments were left out', async () => {
    serveChat(true);

    renderApp(CHAT);

    expect(await screen.findByText('Older comments were left out to fit.')).toBeVisible();
  });

  it('sends what the person edited, linked to the thread', async () => {
    const sent = serveChat();
    renderApp(CHAT);
    const user = userEvent.setup();
    await screen.findByRole('textbox', { name: /What should change/ });

    await user.keyboard('Allow weekly bookings{Enter}');

    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]).toMatchObject({
      kind: 'change_request',
      discussion_thread_id: THREAD_ID,
      text: `Allow weekly bookings\n\n${QUOTE}`,
      base_version_id: BACKLOG.id,
    });
  });

  it('lets an approver who cannot edit send it', async () => {
    const sent = serveChat();
    server.use(http.get(`${API}/me`, () => HttpResponse.json(APPROVER)));
    renderApp(CHAT);
    const user = userEvent.setup();
    const box = await screen.findByRole('textbox', { name: /What should change/ });
    await waitFor(() => {
      expect(box).toBeEnabled();
    });

    await user.keyboard('Allow weekly bookings{Enter}');

    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
  });

  it('forgets the quote when dropped', async () => {
    serveChat();
    const router = renderApp(CHAT);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Do not use this discussion' }));

    expect(router.state.location.search).toBe('');
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'Message ScopeSteps' })).toHaveValue('');
    });
  });

  it('reports a thread it cannot quote', async () => {
    serveChat();
    server.use(
      http.get(`${API}/threads/${THREAD_ID}/change-request-draft`, () =>
        HttpResponse.json(errorBody('PERMISSION_DENIED', 'You cannot do this'), { status: 403 }),
      ),
    );

    renderApp(CHAT);

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not quote the discussion.');
  });

  it('shows on the thread what it was sent as, with a link and status', async () => {
    serveThreads([thread({ change_requests: [{ id: CR_ID, number: 4, status: 'in_review' }] })]);

    renderApp(DISCUSSION);

    const list = await screen.findByRole('list', { name: 'Sent as change request' });
    expect(within(list).getByText('Sent as change request')).toBeVisible();
    expect(within(list).getByRole('link', { name: 'CR-4' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/changes?request=${CR_ID}`,
    );
    expect(within(list).getByText('In review')).toBeVisible();
  });

  it('links a change request back to its discussion', async () => {
    server.use(
      http.get(CHANGE_REQUESTS_URL, () =>
        HttpResponse.json({
          change_requests: [
            changeRequest({ discussion: { thread_id: THREAD_ID, item_title: 'Book a room' } }),
          ],
          next_cursor: null,
        }),
      ),
    );

    serveChat();
    renderApp(`/projects/${PROJECT_ID}/changes`);

    expect(
      await screen.findByRole('link', { name: 'From discussion on Book a room' }),
    ).toHaveAttribute('href', `${DISCUSSION}?thread=${THREAD_ID}`);
  });

  it('names General discussion for a thread on no item', async () => {
    server.use(
      http.get(CHANGE_REQUESTS_URL, () =>
        HttpResponse.json({
          change_requests: [
            changeRequest({ discussion: { thread_id: THREAD_ID, item_title: null } }),
          ],
          next_cursor: null,
        }),
      ),
    );

    serveChat();
    renderApp(`/projects/${PROJECT_ID}/changes`);

    expect(
      await screen.findByRole('link', { name: 'From discussion on General discussion' }),
    ).toBeVisible();
  });
});
