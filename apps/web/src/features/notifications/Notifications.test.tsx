import type { components } from '@scopesteps/api-client';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT_ID, REVIEWER_ID } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import { badgeText, CHECK_EVERY_MS } from './types';

type Notification = components['schemas']['NotificationResponse'];
type Thread = components['schemas']['ThreadResponse'];

const PAGE = `/projects/${PROJECT_ID}/sources`;
const NOW = '2026-10-30T09:00:00Z';
const THREAD_ID = '019a3a5e-0000-7000-8000-0000000000b1';
const COMMENT_ID = '019a3a5e-0000-7000-8000-0000000000b2';
const NOTIFICATION_ID = '019a3a5e-0000-7000-8000-0000000000d1';

function notification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: NOTIFICATION_ID,
    kind: 'mentioned',
    project_id: PROJECT_ID,
    project_name: 'Room booking',
    item: { id: '019a3a5e-0000-7000-8000-0000000000e2', kind: 'story', title: 'Book a room' },
    thread_id: THREAD_ID,
    comment_id: COMMENT_ID,
    actor_id: REVIEWER_ID,
    actor_name: 'Sam Okafor',
    created_at: NOW,
    read_at: null,
    ...overrides,
  };
}

const THREAD: Thread = {
  id: THREAD_ID,
  project_id: PROJECT_ID,
  item_id: null,
  item: null,
  status: 'resolved',
  revision: 2,
  created_by: REVIEWER_ID,
  created_at: NOW,
  last_activity_at: NOW,
  resolved_at: NOW,
  resolved_by: REVIEWER_ID,
  resolved_by_name: 'Sam Okafor',
  comments: [
    {
      id: COMMENT_ID,
      author_id: REVIEWER_ID,
      author_name: 'Sam Okafor',
      body: 'Could you look at this?',
      mentions: [],
      deleted: false,
      revision: 1,
      backlog_version_id: null,
      created_at: NOW,
      edited_at: null,
    },
  ],
  following: true,
  participants: [],
  change_requests: [],
};

function serve(list: Notification[]) {
  const read: string[] = [];
  server.use(
    http.get(`${API}/me/notifications/unread-count`, () =>
      HttpResponse.json({ unread: list.filter((n) => n.read_at === null).length }),
    ),
    http.get(`${API}/me/notifications`, () =>
      HttpResponse.json({ notifications: list, next_cursor: null }),
    ),
    http.post(`${API}/me/notifications/read-all`, () => {
      list.forEach((n) => {
        n.read_at = NOW;
      });
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(`${API}/me/notifications/:id/read`, ({ params }) => {
      read.push(params.id as string);
      list.forEach((n) => {
        if (n.id === params.id) {
          n.read_at = NOW;
        }
      });
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return read;
}

beforeEach(() => {
  server.use(...projectHandlers());
});

describe('The bell', () => {
  it('counts exactly up to nine', () => {
    expect(badgeText(9)).toBe('9');
    expect(badgeText(10)).toBe('9+');
  });

  it('has a text label for the unread count', async () => {
    serve([
      notification(),
      notification({ id: '019a3a5e-0000-7000-8000-0000000000d2' }),
      notification({ id: '019a3a5e-0000-7000-8000-0000000000d3' }),
    ]);

    renderApp(PAGE);

    expect(await screen.findByRole('button', { name: '3 unread notifications' })).toBeVisible();
    await expectNoAccessibilityViolations();
  });

  it('shows 9+ above nine', async () => {
    serve(
      Array.from({ length: 12 }, (_, index) =>
        notification({ id: `019a3a5e-0000-7000-8000-${String(index).padStart(12, '0')}` }),
      ),
    );

    renderApp(PAGE);

    const bell = await screen.findByRole('button', { name: '12 unread notifications' });
    expect(within(bell).getByText('9+')).toBeVisible();
  });

  it('checks for news every 30 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const list: Notification[] = [];
      serve(list);
      renderApp(PAGE);
      await screen.findByRole('button', { name: 'Notifications' });

      list.push(notification());
      await act(() => vi.advanceTimersByTimeAsync(CHECK_EVERY_MS));

      expect(await screen.findByRole('button', { name: '1 unread notification' })).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it('lists who, what, the item and the project, newest first, unread in bold', async () => {
    serve([
      notification(),
      notification({
        id: '019a3a5e-0000-7000-8000-0000000000d2',
        kind: 'replied',
        item: null,
        read_at: NOW,
      }),
    ]);
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: '1 unread notification' }));

    const panel = await screen.findByRole('dialog', { name: 'Notifications' });
    const newest = await within(panel).findByRole('button', {
      name: /Sam Okafor mentioned you on Book a room/,
    });
    expect(newest).toHaveTextContent('Room booking');
    expect(newest).toHaveClass('font-semibold');
    const older = within(panel).getByRole('button', {
      name: /Sam Okafor replied on General discussion/,
    });
    expect(older).not.toHaveClass('font-semibold');
    await expectNoAccessibilityViolations();
  });

  it('says so when there is nothing to read', async () => {
    serve([]);
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Notifications' }));

    expect(await screen.findByText('You’re all caught up')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeDisabled();
  });

  it('reports a list it could not load', async () => {
    serve([]);
    server.use(
      http.get(`${API}/me/notifications`, () =>
        HttpResponse.json(errorBody('INTERNAL', 'Something went wrong'), { status: 500 }),
      ),
    );
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Notifications' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load');
  });

  it('marks everything read', async () => {
    serve([notification()]);
    renderApp(PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '1 unread notification' }));

    await user.click(await screen.findByRole('button', { name: 'Mark all as read' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Notifications', expanded: true })).toBeVisible();
    });
  });

  it('closes on Escape and gives focus back', async () => {
    serve([]);
    renderApp(PAGE);
    const user = userEvent.setup();
    const bell = await screen.findByRole('button', { name: 'Notifications' });
    await user.click(bell);
    await screen.findByRole('dialog');

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(bell).toHaveFocus();
  });

  it('opens the comment, resolved thread or not, highlighted, and marks it read', async () => {
    const read = serve([notification()]);
    server.use(http.get(`${API}/threads/${THREAD_ID}`, () => HttpResponse.json(THREAD)));
    const router = renderApp(PAGE);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: '1 unread notification' }));

    await user.click(await screen.findByRole('button', { name: /Sam Okafor mentioned you/ }));

    await waitFor(() => {
      expect(read).toEqual([NOTIFICATION_ID]);
    });
    expect(router.state.location.pathname).toBe(`/projects/${PROJECT_ID}/discussion`);
    expect(router.state.location.search).toBe(`?thread=${THREAD_ID}&comment=${COMMENT_ID}`);
    const article = await screen.findByRole('article');
    expect(article).toHaveAttribute('aria-current', 'true');
    expect(within(article).getByText('Could you look at this?')).toBeVisible();
  });

  it('says so when the discussion is gone', async () => {
    serve([]);
    server.use(
      http.get(`${API}/threads/${THREAD_ID}`, () =>
        HttpResponse.json(errorBody('NOT_FOUND', 'Discussion not found'), { status: 404 }),
      ),
    );

    renderApp(`/projects/${PROJECT_ID}/discussion?thread=${THREAD_ID}`);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This discussion is no longer available.',
    );
    expect(screen.getByRole('link', { name: 'Show all discussions' })).toBeVisible();
  });
});

describe('Email choices in the profile', () => {
  function serveSettings(fail = false) {
    const saved: unknown[] = [];
    server.use(
      http.get(`${API}/me/notification-settings`, () =>
        HttpResponse.json({ email_on_mention: true, email_on_reply: false }),
      ),
      http.put(`${API}/me/notification-settings`, async ({ request }) => {
        if (fail) {
          return HttpResponse.json(errorBody('INTERNAL', 'Something went wrong'), { status: 500 });
        }
        const body = await request.json();
        saved.push(body);
        return HttpResponse.json(body);
      }),
    );
    return saved;
  }

  async function openProfile(user: ReturnType<typeof userEvent.setup>) {
    renderApp(PAGE);
    await user.click(await screen.findByRole('button', { name: /Sample|Reviewer|account/i }));
    await user.click(await screen.findByRole('menuitem', { name: /Settings/ }));
  }

  it('starts with mentions on and replies off, and saves a change', async () => {
    const saved = serveSettings();
    serve([]);
    const user = userEvent.setup();
    await openProfile(user);

    const mentions = await screen.findByRole('checkbox', { name: 'Email me when I’m mentioned' });
    const replies = screen.getByRole('checkbox', {
      name: 'Email me about replies to threads I follow',
    });
    expect(mentions).toBeChecked();
    expect(replies).not.toBeChecked();

    await user.click(replies);

    await waitFor(() => {
      expect(saved).toEqual([{ email_on_mention: true, email_on_reply: true }]);
    });
    expect(replies).toBeChecked();
  });

  it('shows an error when a choice was not saved', async () => {
    serveSettings(true);
    serve([]);
    const user = userEvent.setup();
    await openProfile(user);

    await user.click(await screen.findByRole('checkbox', { name: 'Email me when I’m mentioned' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Your choice was not saved.');
  });
});
