import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT_ID, REVIEWER, REVIEWER_ID, VIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Thread = components['schemas']['ThreadResponse'];
type Comment = components['schemas']['CommentResponse'];

const PAGE = `/projects/${PROJECT_ID}/discussion`;
const NOW = '2026-10-30T09:00:00Z';
const THREAD_ID = '019a3a5e-0000-7000-8000-0000000000b1';
const COMMENT_ID = '019a3a5e-0000-7000-8000-0000000000b2';
const SAM_ID = '019a3a5e-0000-7000-8000-0000000000c1';
const DANA_ID = '019a3a5e-0000-7000-8000-0000000000c2';
const MEMBERS = [
  { user_id: DANA_ID, display_name: 'Dana Ruiz', role: 'approver' },
  { user_id: SAM_ID, display_name: 'Sam Okafor', role: 'viewer' },
];

function comment(overrides: Partial<Comment> = {}): Comment {
  return {
    id: COMMENT_ID,
    author_id: SAM_ID,
    author_name: 'Sam Okafor',
    body: 'A thought',
    mentions: [],
    deleted: false,
    revision: 1,
    backlog_version_id: null,
    created_at: NOW,
    edited_at: null,
    ...overrides,
  };
}

function thread(overrides: Partial<Thread> = {}): Thread {
  return {
    id: THREAD_ID,
    project_id: PROJECT_ID,
    item_id: null,
    item: null,
    status: 'open',
    revision: 1,
    created_by: SAM_ID,
    created_at: NOW,
    last_activity_at: NOW,
    resolved_at: null,
    resolved_by: null,
    resolved_by_name: null,
    comments: [comment()],
    following: true,
    change_requests: [],
    ...overrides,
  };
}

function serve(threads: Thread[]) {
  const started: string[] = [];
  const followed: boolean[] = [];
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}/threads`, () =>
      HttpResponse.json({ threads, next_cursor: null }),
    ),
    http.get(`${API}/projects/${PROJECT_ID}/members/search`, ({ request }) => {
      const query = (new URL(request.url).searchParams.get('q') ?? '').toLowerCase();
      return HttpResponse.json({
        members: MEMBERS.filter((m) => m.display_name.toLowerCase().includes(query)),
      });
    }),
    http.post(`${API}/projects/${PROJECT_ID}/threads`, async ({ request }) => {
      const { body } = (await request.json()) as { body: string };
      started.push(body);
      return HttpResponse.json(thread({ comments: [comment({ body })] }), { status: 201 });
    }),
    http.put(`${API}/threads/${THREAD_ID}/follow`, async ({ request }) => {
      const { following } = (await request.json()) as { following: boolean };
      followed.push(following);
      const [first] = threads;
      if (first) {
        first.following = following;
      }
      return HttpResponse.json(first);
    }),
  );
  return { started, followed };
}

async function box() {
  return screen.findByRole('textbox', { name: 'Start a General discussion' });
}

beforeEach(() => {
  window.sessionStorage.clear();
  server.use(...projectHandlers());
});

describe('Mentioning someone', () => {
  it('opens the members on @, filters as you type, and shows names with roles', async () => {
    serve([]);
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.type(await box(), 'Over to @');

    const list = await screen.findByRole('listbox', { name: 'Project members' });
    expect(within(list).getAllByRole('option')).toHaveLength(2);
    expect(within(list).getByText('Product owner')).toBeVisible();

    await user.type(await box(), 'sam');

    await waitFor(() => {
      expect(screen.getAllByRole('option')).toHaveLength(1);
    });
    await expectNoAccessibilityViolations();
  });

  it('picks with the arrows and Enter, and posts the person by id', async () => {
    const { started } = serve([]);
    renderApp(PAGE);
    const user = userEvent.setup();
    const input = await box();

    await user.type(input, 'Over to @');
    await screen.findByRole('listbox');
    expect(input).toHaveAttribute('aria-activedescendant');
    await user.keyboard('{ArrowDown}{Enter}');

    expect(input).toHaveValue('Over to @Sam Okafor ');
    expect(screen.getByText('@Sam Okafor', { selector: 'mark' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Start discussion' }));
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(started).toEqual([`Over to <@${SAM_ID}> `]);
    });
  });

  it('picks with a click', async () => {
    serve([]);
    renderApp(PAGE);
    const user = userEvent.setup();
    const input = await box();

    await user.type(input, '@');
    await user.click(await screen.findByRole('option', { name: /Dana Ruiz/ }));

    expect(input).toHaveValue('@Dana Ruiz ');
  });

  it('closes the list on Escape and keeps what was typed', async () => {
    serve([]);
    renderApp(PAGE);
    const user = userEvent.setup();
    const input = await box();

    await user.type(input, '@sa');
    await screen.findByRole('listbox');
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(input).toHaveValue('@sa');
  });

  it('removes a mention whole with Backspace', async () => {
    const { started } = serve([]);
    renderApp(PAGE);
    const user = userEvent.setup();
    const input = await box();
    await user.type(input, '@');
    await screen.findByRole('listbox');
    await user.keyboard('{Enter}');

    await user.keyboard('{Backspace}{Backspace}');

    expect(input).toHaveValue('');
    await user.type(input, 'Plain');
    await user.click(screen.getByRole('button', { name: 'Start discussion' }));
    await waitFor(() => {
      expect(started).toEqual(['Plain']);
    });
  });

  it('keeps a picked mention in an unsent draft across a reload of the box', async () => {
    serve([]);
    const first = renderApp(PAGE);
    const user = userEvent.setup();
    await user.type(await box(), '@');
    await screen.findByRole('listbox');
    await user.keyboard('{Enter}');
    await first.navigate(`/projects/${PROJECT_ID}/activity`);
    await first.navigate(PAGE);

    expect(await box()).toHaveValue('@Dana Ruiz ');
    expect(screen.getByText('@Dana Ruiz', { selector: 'mark' })).toBeInTheDocument();
  });

  it('shows the server’s refusal of someone no longer in the project', async () => {
    serve([]);
    server.use(
      http.post(`${API}/projects/${PROJECT_ID}/threads`, () =>
        HttpResponse.json(
          errorBody('MENTION_NOT_MEMBER', 'Only current members can be mentioned'),
          {
            status: 422,
          },
        ),
      ),
    );
    renderApp(PAGE);
    const user = userEvent.setup();
    await user.type(await box(), 'Hello');

    await user.click(screen.getByRole('button', { name: 'Start discussion' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Only current members can be mentioned',
    );
  });
});

describe('A rendered mention', () => {
  it('shows the current name, and the reader’s own name more strongly', async () => {
    serve([
      thread({
        comments: [
          comment({
            body: `Ask <@${DANA_ID}> or <@${REVIEWER_ID}>`,
            mentions: [
              { user_id: DANA_ID, display_name: 'Dana Ruiz' },
              { user_id: REVIEWER_ID, display_name: REVIEWER.display_name },
            ],
          }),
        ],
      }),
    ]);

    renderApp(PAGE);

    const dana = await screen.findByText('@Dana Ruiz');
    const mine = screen.getByText(`@${REVIEWER.display_name}`);
    expect(dana).toHaveClass('bg-accent-soft');
    expect(mine).toHaveClass('bg-accent');
    expect(screen.queryByText(/<@/)).not.toBeInTheDocument();
  });

  it('edits a comment by the names, not the tokens', async () => {
    serve([
      thread({
        comments: [
          comment({
            author_id: REVIEWER_ID,
            body: `Ask <@${DANA_ID}>`,
            mentions: [{ user_id: DANA_ID, display_name: 'Dana Ruiz' }],
          }),
        ],
      }),
    ]);
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Edit' }));

    expect(screen.getByRole('textbox', { name: 'Edit comment' })).toHaveValue('Ask @Dana Ruiz');
  });
});

describe('Following a thread', () => {
  it('toggles and says which state it is in', async () => {
    const { followed } = serve([thread()]);
    renderApp(PAGE);
    const user = userEvent.setup();

    const toggle = await screen.findByRole('button', { name: 'Following' });
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await user.click(toggle);

    expect(await screen.findByRole('button', { name: 'Follow' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(followed).toEqual([false]);
  });

  it('shows an error when the choice was not saved', async () => {
    serve([thread()]);
    server.use(
      http.put(`${API}/threads/${THREAD_ID}/follow`, () =>
        HttpResponse.json(errorBody('INTERNAL', 'Something went wrong'), { status: 500 }),
      ),
    );
    renderApp(PAGE);
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Following' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong');
  });

  it('is offered to a viewer too', async () => {
    serve([thread()]);
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));

    renderApp(PAGE);

    expect(await screen.findByRole('button', { name: 'Following' })).toBeVisible();
  });
});
