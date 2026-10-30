import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BACKLOG,
  errorBody,
  PROJECT_ID,
  REVIEWER,
  REVIEWER_ID,
  STORY_ID,
  VERSION_ID,
  VIEWER,
} from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { resetViewport, setNarrowViewport } from '@/test/viewport';

type Thread = components['schemas']['ThreadResponse'];
type Comment = components['schemas']['CommentResponse'];

const OTHER_ID = '019a3a5e-0000-7000-8000-0000000000c9';
const DISCUSSION_PAGE = `/projects/${PROJECT_ID}/discussion`;
const BACKLOG_PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const STORY_TITLE = 'Search for and book a one-off slot';
const NOW = '2026-10-29T09:00:00Z';

let ids = 0;
function nextId(): string {
  ids += 1;
  return `019a3a5e-0000-7000-8000-${ids.toString(16).padStart(12, '0')}`;
}

function comment(body: string, author = { id: OTHER_ID, name: 'Sam Okafor' }): Comment {
  return {
    id: nextId(),
    author_id: author.id,
    author_name: author.name,
    body,
    deleted: false,
    revision: 1,
    backlog_version_id: VERSION_ID,
    created_at: NOW,
    edited_at: null,
  };
}

const ME = { id: REVIEWER_ID, name: REVIEWER.display_name };

function thread(first: Comment, overrides: Partial<Thread> = {}): Thread {
  return {
    id: nextId(),
    project_id: PROJECT_ID,
    item_id: null,
    item: null,
    status: 'open',
    revision: 1,
    created_by: first.author_id,
    created_at: NOW,
    last_activity_at: NOW,
    resolved_at: null,
    resolved_by: null,
    resolved_by_name: null,
    comments: [first],
    ...overrides,
  };
}

function onStory(): Partial<Thread> {
  return {
    item_id: STORY_ID,
    item: { id: STORY_ID, kind: 'story', title: STORY_TITLE, in_current_backlog: true },
  };
}

/** The discussion endpoints over an in-memory list, as the API answers them. */
function serveDiscussions(threads: Thread[]) {
  const find = (id: string | undefined) => threads.find((t) => t.id === id);
  const owner = (commentId: string | undefined) =>
    threads.find((t) => t.comments.some((c) => c.id === commentId));
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}/threads/counts`, () => {
      const open = threads.filter((t) => t.status === 'open');
      const items = [...new Set(open.flatMap((t) => (t.item_id ? [t.item_id] : [])))];
      return HttpResponse.json({
        items: items.map((itemId) => ({
          item_id: itemId,
          open_threads: open.filter((t) => t.item_id === itemId).length,
        })),
        general_open_threads: open.filter((t) => t.item_id === null).length,
      });
    }),
    http.get(`${API}/projects/${PROJECT_ID}/threads`, ({ request }) => {
      const query = new URL(request.url).searchParams;
      const status = query.get('status') ?? 'all';
      const itemId = query.get('item_id');
      const listed = threads.filter(
        (t) => (status === 'all' || t.status === status) && (!itemId || t.item_id === itemId),
      );
      return HttpResponse.json({ threads: [...listed].reverse(), next_cursor: null });
    }),
    http.post(`${API}/projects/${PROJECT_ID}/threads`, async ({ request }) => {
      const body = (await request.json()) as { body: string; item_id: string | null };
      const first = comment(body.body.trim(), ME);
      const started = thread(first, {
        created_by: REVIEWER_ID,
        ...(body.item_id ? onStory() : {}),
      });
      threads.push(started);
      return HttpResponse.json(started, { status: 201 });
    }),
    http.post(`${API}/threads/:threadId/comments`, async ({ params, request }) => {
      const found = find(params.threadId as string);
      if (!found) {
        return HttpResponse.json(errorBody('NOT_FOUND', 'Discussion not found'), { status: 404 });
      }
      const body = (await request.json()) as { body: string };
      found.comments.push(comment(body.body.trim(), ME));
      return HttpResponse.json(found, { status: 201 });
    }),
    http.patch(`${API}/comments/:commentId`, async ({ params, request }) => {
      const found = owner(params.commentId as string);
      const target = found?.comments.find((c) => c.id === params.commentId);
      const body = (await request.json()) as { body: string; expected_revision: number };
      if (!found || !target) {
        return HttpResponse.json(errorBody('NOT_FOUND', 'Comment not found'), { status: 404 });
      }
      if (target.revision !== body.expected_revision) {
        return HttpResponse.json(errorBody('COMMENT_CHANGED', 'Changed'), { status: 409 });
      }
      Object.assign(target, { body: body.body, revision: target.revision + 1, edited_at: NOW });
      return HttpResponse.json(found);
    }),
    http.delete(`${API}/comments/:commentId`, ({ params }) => {
      const found = owner(params.commentId as string);
      if (found) {
        found.comments = found.comments.filter((c) => c.id !== params.commentId);
        // A thread with nothing left is gone from every list, as in the API.
        if (found.comments.length === 0) {
          threads.splice(threads.indexOf(found), 1);
        }
      }
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(`${API}/threads/:threadId/:action`, async ({ params, request }) => {
      const found = find(params.threadId as string);
      const body = (await request.json()) as { expected_revision: number };
      if (!found) {
        return HttpResponse.json(errorBody('NOT_FOUND', 'Discussion not found'), { status: 404 });
      }
      if (found.revision !== body.expected_revision) {
        return HttpResponse.json(errorBody('THREAD_CHANGED', 'Someone changed this discussion'), {
          status: 409,
        });
      }
      Object.assign(found, {
        status: params.action === 'resolve' ? 'resolved' : 'open',
        revision: found.revision + 1,
        resolved_by_name: params.action === 'resolve' ? ME.name : null,
      });
      return HttpResponse.json(found);
    }),
  );
}

function main() {
  return within(screen.getByRole('main'));
}

async function threadCard(text: string) {
  const list = await main().findByRole('list', { name: 'Discussions' });
  const item = within(list)
    .getAllByRole('listitem')
    .find((li) => li.textContent.includes(text));
  if (!item) {
    throw new Error(`No thread containing ${text}`);
  }
  return within(item);
}

beforeEach(() => {
  ids = 0;
  window.localStorage.clear();
  window.sessionStorage.clear();
  server.use(...projectHandlers());
});

afterEach(() => {
  resetViewport();
});

describe('The Discussion page', () => {
  it('says there are no discussions yet and how to start one', async () => {
    serveDiscussions([]);

    renderApp(DISCUSSION_PAGE);

    expect(await main().findByRole('heading', { name: 'No discussions yet' })).toBeVisible();
    expect(
      main().getByText('Start one to keep talk about this item in one place.'),
    ).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('lists threads with author, time, version and what each is about', async () => {
    const first = comment('Should bookings repeat weekly?');
    serveDiscussions([thread(first, onStory()), thread(comment('A general idea'))]);
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs`, () =>
        HttpResponse.json({
          versions: [
            {
              id: VERSION_ID,
              state: 'approved',
              revision: 1,
              number: 2,
              content_hash: 'b'.repeat(64),
              base_version_id: null,
              run_id: null,
              created_by: REVIEWER_ID,
              created_at: NOW,
              decision: null,
            },
          ],
          next_cursor: null,
        }),
      ),
    );

    renderApp(DISCUSSION_PAGE);

    const story = await threadCard('Should bookings repeat weekly?');
    expect(story.getByText(`Story · ${STORY_TITLE}`)).toBeInTheDocument();
    expect(story.getByText('Sam Okafor')).toBeInTheDocument();
    expect(await story.findByText('about v2')).toBeInTheDocument();
    expect(story.getByRole('article').querySelector('time')).toHaveAttribute('dateTime', NOW);
    expect((await threadCard('A general idea')).getByText('General discussion')).toBeVisible();
  });

  it('shows comment text with HTML or script as plain text, and web addresses as links', async () => {
    const hostile =
      '<img src=x onerror=alert(1)><script>alert(2)</script> see https://example.test/brief';
    serveDiscussions([thread(comment(hostile))]);

    renderApp(DISCUSSION_PAGE);

    const card = await threadCard('<script>alert(2)</script>');
    expect(card.getByText(/<img src=x onerror=alert\(1\)>/)).toBeInTheDocument();
    expect(document.querySelector('main img, main script')).toBeNull();
    expect(card.getByRole('link', { name: 'https://example.test/brief' })).toHaveAttribute(
      'rel',
      'noopener noreferrer nofollow',
    );
  });

  it('starts a General discussion with Cmd+Enter and moves focus to it', async () => {
    serveDiscussions([]);
    renderApp(DISCUSSION_PAGE);
    const box = await main().findByRole('textbox', { name: 'Start a General discussion' });

    await userEvent.type(box, 'Ask the sponsor about weekends{Meta>}{Enter}{/Meta}');

    const card = await threadCard('Ask the sponsor about weekends');
    await waitFor(() => {
      expect(card.getByRole('article')).toHaveFocus();
    });
    expect(box).toHaveValue('');
  });

  it('replies under a thread, newest last, and keeps an unsent reply when the page is left', async () => {
    serveDiscussions([thread(comment('Weekends too?'))]);
    const router = renderApp(DISCUSSION_PAGE);
    let card = await threadCard('Weekends too?');

    await userEvent.type(card.getByRole('textbox', { name: 'Reply' }), 'Half-written');
    await router.navigate(`/projects/${PROJECT_ID}/activity`);
    await router.navigate(DISCUSSION_PAGE);
    card = await threadCard('Weekends too?');
    const reply = card.getByRole('textbox', { name: 'Reply' });
    expect(reply).toHaveValue('Half-written');

    await userEvent.clear(reply);
    await userEvent.type(reply, 'Only for staff');
    await userEvent.click(card.getByRole('button', { name: 'Reply' }));

    await waitFor(() => {
      expect(card.getAllByRole('article').map((a) => a.querySelector('p')?.textContent)).toEqual([
        'Weekends too?',
        'Only for staff',
      ]);
    });
  });

  it('lets the author edit their comment, which then shows as edited', async () => {
    serveDiscussions([thread(comment('Typo hre', ME))]);
    renderApp(DISCUSSION_PAGE);
    const card = await threadCard('Typo hre');

    await userEvent.click(card.getByRole('button', { name: 'Edit' }));
    const field = card.getByRole('textbox', { name: 'Edit comment' });
    await userEvent.clear(field);
    await userEvent.type(field, 'Typo here');
    await userEvent.click(card.getByRole('button', { name: 'Save' }));

    expect(await card.findByText('Typo here')).toBeInTheDocument();
    expect(card.getByText('edited')).toBeInTheDocument();
  });

  it('deletes the author’s comment only after they confirm', async () => {
    serveDiscussions([thread(comment('Never mind', ME))]);
    renderApp(DISCUSSION_PAGE);
    const card = await threadCard('Never mind');

    await userEvent.click(card.getByRole('button', { name: 'Delete' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Delete this comment?' }));
    await userEvent.click(dialog.getByRole('button', { name: 'Keep it' }));
    expect(card.getByText('Never mind')).toBeInTheDocument();

    await userEvent.click(card.getByRole('button', { name: 'Delete' }));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Delete comment' }),
    );

    expect(await main().findByRole('heading', { name: 'No discussions yet' })).toBeVisible();
  });

  it('shows a deleted first comment as a placeholder', async () => {
    const gone = { ...comment(''), body: null, deleted: true };
    serveDiscussions([thread(gone, { comments: [gone, comment('Still relevant')] })]);

    renderApp(DISCUSSION_PAGE);

    const card = await threadCard('Still relevant');
    expect(card.getByText('Comment deleted')).toBeInTheDocument();
  });

  it('offers Edit and Delete only on the user’s own comments', async () => {
    const first = comment('Theirs');
    serveDiscussions([thread(first, { comments: [first, comment('Mine', ME)] })]);
    renderApp(DISCUSSION_PAGE);
    const card = await threadCard('Theirs');

    const [theirs, mine] = card.getAllByRole('article');
    expect(within(theirs ?? document.body).queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(within(theirs ?? document.body).queryByRole('button', { name: 'Delete' })).toBeNull();
    expect(within(mine ?? document.body).getByRole('button', { name: 'Edit' })).toBeVisible();
    expect(within(mine ?? document.body).getByRole('button', { name: 'Delete' })).toBeVisible();
  });

  it('resolves a thread, folds it to one line, and reopens it', async () => {
    serveDiscussions([thread(comment('Decide on weekends'))]);
    renderApp(DISCUSSION_PAGE);
    await userEvent.click(await main().findByRole('button', { name: 'All' }));
    let card = await threadCard('Decide on weekends');

    await userEvent.click(card.getByRole('button', { name: 'Resolve' }));

    card = await threadCard('Decide on weekends');
    expect(await card.findByText('Resolved')).toBeInTheDocument();
    expect(card.queryByRole('textbox', { name: 'Reply' })).toBeNull();
    expect(card.queryByRole('article')).toBeNull();
    await userEvent.click(card.getByRole('button', { name: 'Show comment' }));
    expect(card.getByRole('article')).toBeVisible();

    await userEvent.click(card.getByRole('button', { name: 'Reopen' }));

    expect(await card.findByRole('textbox', { name: 'Reply' })).toBeVisible();
  });

  it('hides Resolve from a viewer on someone else’s thread but not on their own', async () => {
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));
    serveDiscussions([thread(comment('Theirs')), thread(comment('Mine', ME))]);
    renderApp(DISCUSSION_PAGE);

    expect((await threadCard('Theirs')).queryByRole('button', { name: 'Resolve' })).toBeNull();
    expect((await threadCard('Mine')).getByRole('button', { name: 'Resolve' })).toBeVisible();
  });

  it('asks to reload when someone else changed the thread first', async () => {
    const stale = thread(comment('Racing'));
    serveDiscussions([stale]);
    renderApp(DISCUSSION_PAGE);
    const card = await threadCard('Racing');
    stale.revision = 5;

    await userEvent.click(card.getByRole('button', { name: 'Resolve' }));

    const alert = await card.findByRole('alert');
    expect(alert).toHaveTextContent('Someone changed this discussion since you opened it');
    await userEvent.click(within(alert).getByRole('button', { name: 'Reload' }));
    await waitFor(() => {
      expect(card.queryByRole('alert')).toBeNull();
    });
  });

  it('shows the server’s refusal when a comment is too long', async () => {
    serveDiscussions([]);
    server.use(
      http.post(`${API}/projects/${PROJECT_ID}/threads`, () =>
        HttpResponse.json(
          errorBody('COMMENT_TOO_LONG', 'A comment can be at most 5,000 characters'),
          { status: 422 },
        ),
      ),
    );
    renderApp(DISCUSSION_PAGE);

    await userEvent.type(
      await main().findByRole('textbox', { name: 'Start a General discussion' }),
      'Long',
    );
    await userEvent.click(main().getByRole('button', { name: 'Start discussion' }));

    expect(await main().findByRole('alert')).toHaveTextContent(
      'A comment can be at most 5,000 characters',
    );
    expect(main().getByRole('textbox', { name: 'Start a General discussion' })).toHaveValue('Long');
  });

  it('works at phone width', async () => {
    setNarrowViewport(true);
    serveDiscussions([thread(comment('On a phone'))]);

    renderApp(DISCUSSION_PAGE);

    await threadCard('On a phone');
    await expectNoAccessibilityViolations();
  });
});

describe('Discussions on the backlog', () => {
  beforeEach(() => {
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
        HttpResponse.json(BACKLOG),
      ),
    );
  });

  it('shows each item’s open thread count and updates it after posting and resolving', async () => {
    const first = comment('Already talking');
    serveDiscussions([thread(first, onStory())]);
    renderApp(BACKLOG_PAGE);

    const bubble = await main().findByRole('button', {
      name: `Discussion on ${STORY_TITLE}, 1 open thread`,
    });
    await userEvent.click(bubble);
    const sheet = within(
      await screen.findByRole('dialog', { name: `Discussion · ${STORY_TITLE}` }),
    );
    await userEvent.type(
      sheet.getByRole('textbox', { name: 'Start a discussion' }),
      'What about staff?',
    );
    await userEvent.click(sheet.getByRole('button', { name: 'Start discussion' }));

    expect(
      await main().findByRole('button', { name: `Discussion on ${STORY_TITLE}, 2 open threads` }),
    ).toBeInTheDocument();

    const list = within(sheet.getByRole('list', { name: 'Discussions' }));
    const [newest] = list.getAllByRole('listitem');
    await userEvent.click(within(newest ?? document.body).getByRole('button', { name: 'Resolve' }));

    expect(
      await main().findByRole('button', { name: `Discussion on ${STORY_TITLE}, 1 open thread` }),
    ).toBeInTheDocument();
  });

  it('offers to start a discussion on an item with none', async () => {
    serveDiscussions([]);
    renderApp(BACKLOG_PAGE);

    await userEvent.click(await main().findByRole('button', { name: `Discuss ${STORY_TITLE}` }));

    const sheet = within(
      await screen.findByRole('dialog', { name: `Discussion · ${STORY_TITLE}` }),
    );
    expect(sheet.getByRole('heading', { name: 'No discussions yet' })).toBeVisible();
    await expectNoAccessibilityViolations();
  });
});
