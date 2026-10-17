import type { components } from '@scopesteps/api-client';
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BACKLOG,
  BRIEF,
  errorBody,
  makeRun,
  PROJECT,
  PROJECT_ID,
  TRANSCRIPT,
  VIEWER,
} from '@/test/fixtures';
import { API, MESSAGES_URL, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { Message, Suggestion } from './types';

type Conversation = components['schemas']['ConversationResponse'];

const CHAT = `/projects/${PROJECT_ID}/chat`;
const AT = '2026-10-16T09:00:00Z';
const REPLY_ID = '019a3a5e-0000-7000-8000-0000000000a9';
const BASELINE_ID = '019a3a5e-0000-7000-8000-0000000000e9';
const DECISION_ID = '019a3a5e-0000-7000-8000-000000000301';
const STATUS_URL = `${API}/projects/${PROJECT_ID}/messages/${REPLY_ID}/suggestion`;
const REQUEST_TEXT = 'Allow societies to book the same room every week.';

function suggestion(overrides: Partial<Suggestion>): Suggestion {
  return {
    kind: 'start_draft',
    status: 'offered',
    revision: 1,
    request_text: null,
    version_id: null,
    decision_id: null,
    decision_subject: null,
    answer: null,
    decided_by: null,
    decided_at: null,
    ...overrides,
  };
}

function reply(offered: Suggestion | null): Message {
  return {
    id: REPLY_ID,
    author: null,
    claims: [{ text: 'Recurring bookings are out of scope today.', basis: 'agent', citations: [] }],
    created_at: AT,
    event: null,
    change_request_id: null,
    baseline_version: null,
    kind: 'reply',
    question: null,
    question_id: null,
    role: 'agent',
    run_id: '019a3a5e-0000-7000-8000-0000000000f2',
    text: '',
    suggestion: offered,
  };
}

function serveThread(offered: Suggestion | null) {
  const state = { current: offered };
  server.use(
    http.get(MESSAGES_URL, () =>
      HttpResponse.json<Conversation>({
        messages: [reply(state.current)],
        next_cursor: null,
        active_run: null,
      }),
    ),
  );
  return state;
}

interface Sent {
  key: string | null;
  body: unknown;
}

function recordTo(method: 'post' | 'put' | 'patch', url: string, respond: () => Response) {
  const sent: Sent[] = [];
  server.use(
    http[method](url, async ({ request }) => {
      sent.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      return respond();
    }),
  );
  return sent;
}

function withBaseline() {
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        status: {
          state: 'baseline',
          baseline_version: 1,
          baseline_version_id: BASELINE_ID,
          open_version_id: null,
        },
      }),
    ),
    http.get(`${API}/projects/${PROJECT_ID}/backlogs/${BASELINE_ID}`, () =>
      HttpResponse.json({ ...BACKLOG, id: BASELINE_ID, state: 'approved' }),
    ),
  );
}

function card() {
  return within(screen.getByRole('region', { name: /^Suggested:/ }));
}

async function shownCard() {
  return within(await screen.findByRole('region', { name: /^Suggested:/ }));
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  server.use(...projectHandlers());
});

describe('Suggestion cards', () => {
  it('shows a change request with its exact text and sends nothing until pressed', async () => {
    withBaseline();
    serveThread(suggestion({ kind: 'change_request', request_text: REQUEST_TEXT }));
    const posted = recordTo('post', MESSAGES_URL, () => HttpResponse.json({}, { status: 500 }));
    renderApp(CHAT);

    const shown = within(
      await screen.findByRole('region', { name: 'Suggested: submit a change request' }),
    );

    expect(shown.getByText(REQUEST_TEXT)).toBeVisible();
    expect(shown.getByText('Nothing happens until you press the button.')).toBeVisible();
    expect(shown.getByRole('button', { name: 'Submit change request' })).toBeEnabled();
    expect(posted).toHaveLength(0);
    await expectNoAccessibilityViolations();
  });

  it('submits the change request once, then records it as accepted', async () => {
    withBaseline();
    const thread = serveThread(suggestion({ kind: 'change_request', request_text: REQUEST_TEXT }));
    const posted = recordTo('post', MESSAGES_URL, () =>
      HttpResponse.json(
        { message: reply(null), run: makeRun({ mode: 'change', status: 'created' }) },
        { status: 202 },
      ),
    );
    const recorded = recordTo('put', STATUS_URL, () => {
      thread.current = suggestion({
        kind: 'change_request',
        request_text: REQUEST_TEXT,
        status: 'accepted',
        revision: 2,
      });
      return HttpResponse.json(thread.current);
    });
    renderApp(CHAT);
    const button = await (
      await shownCard()
    ).findByRole('button', { name: 'Submit change request' });

    await userEvent.dblClick(button);

    await waitFor(() => {
      expect(card().getByText('Done')).toBeVisible();
    });
    expect(posted).toHaveLength(1);
    expect(posted[0]?.body).toEqual({
      kind: 'change_request',
      text: REQUEST_TEXT,
      base_version_id: BASELINE_ID,
      base_content_hash: BACKLOG.content_hash,
    });
    expect(posted[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(recorded.map((each) => each.body)).toEqual([
      { status: 'accepted', expected_revision: 1 },
    ]);
    expect(card().getByText('Submitted as a change request.')).toBeVisible();
    expect(card().queryByRole('button')).not.toBeInTheDocument();
  });

  it('answers a decision on the draft with the exact answer it shows', async () => {
    const answer = 'up to two hours before the start';
    serveThread(
      suggestion({
        kind: 'answer_decision',
        version_id: BACKLOG.id,
        decision_id: DECISION_ID,
        decision_subject: 'Cancellation',
        answer,
      }),
    );
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${BACKLOG.id}`, () =>
        HttpResponse.json(BACKLOG),
      ),
    );
    const answered = recordTo(
      'patch',
      `${API}/backlogs/${BACKLOG.id}/decisions/${DECISION_ID}`,
      () => HttpResponse.json(BACKLOG),
    );
    const recorded = recordTo('put', STATUS_URL, () =>
      HttpResponse.json(suggestion({ kind: 'answer_decision', status: 'accepted', revision: 2 })),
    );
    renderApp(CHAT);
    const shown = within(
      await screen.findByRole('region', { name: 'Suggested: answer an open decision' }),
    );
    expect(shown.getByText('Cancellation')).toBeVisible();
    expect(shown.getByText(answer)).toBeVisible();

    await userEvent.click(shown.getByRole('button', { name: 'Answer decision' }));

    await waitFor(() => {
      expect(recorded).toHaveLength(1);
    });
    expect(answered.map((each) => each.body)).toEqual([
      { answer, expected_revision: BACKLOG.revision },
    ]);
  });

  it('starts a draft run from the current sources', async () => {
    serveThread(suggestion({ kind: 'start_draft' }));
    const started = recordTo('post', `${API}/projects/${PROJECT_ID}/runs`, () =>
      HttpResponse.json(makeRun({ status: 'created' }), { status: 202 }),
    );
    const recorded = recordTo('put', STATUS_URL, () =>
      HttpResponse.json(suggestion({ status: 'accepted', revision: 2 })),
    );
    renderApp(CHAT);

    await userEvent.click(await (await shownCard()).findByRole('button', { name: 'Start run' }));

    await waitFor(() => {
      expect(recorded).toHaveLength(1);
    });
    expect(started.map((each) => each.body)).toEqual([
      { mode: 'initial', source_version_ids: [BRIEF.id, TRANSCRIPT.id] },
    ]);
  });

  it('dismisses without taking the step, and shows it dismissed after a reload', async () => {
    const thread = serveThread(suggestion({ kind: 'start_draft' }));
    const started = recordTo('post', `${API}/projects/${PROJECT_ID}/runs`, () =>
      HttpResponse.json({}, { status: 500 }),
    );
    const recorded = recordTo('put', STATUS_URL, () => {
      thread.current = suggestion({ status: 'dismissed', revision: 2 });
      return HttpResponse.json(thread.current);
    });
    renderApp(CHAT);

    await userEvent.click(await (await shownCard()).findByRole('button', { name: 'Dismiss' }));

    await waitFor(() => {
      expect(card().getByText('Dismissed')).toBeVisible();
    });
    expect(recorded.map((each) => each.body)).toEqual([
      { status: 'dismissed', expected_revision: 1 },
    ]);
    expect(started).toHaveLength(0);
    cleanup();
    renderApp(CHAT);
    expect(await (await shownCard()).findByText('Dismissed')).toBeVisible();
    expect(card().queryByRole('button')).not.toBeInTheDocument();
  });

  it('shows a refusal as the server gives it and stays usable', async () => {
    withBaseline();
    serveThread(suggestion({ kind: 'change_request', request_text: REQUEST_TEXT }));
    recordTo('post', MESSAGES_URL, () =>
      HttpResponse.json(
        errorBody('BASELINE_CHANGED', 'The baseline changed since you loaded it.'),
        { status: 409 },
      ),
    );
    const recorded = recordTo('put', STATUS_URL, () => HttpResponse.json({}, { status: 500 }));
    renderApp(CHAT);

    await userEvent.click(
      await (await shownCard()).findByRole('button', { name: 'Submit change request' }),
    );

    expect(await (await shownCard()).findByRole('alert')).toHaveTextContent(
      'Nothing was changed. The baseline changed since you loaded it.',
    );
    expect(card().getByRole('button', { name: 'Submit change request' })).toBeEnabled();
    expect(recorded).toHaveLength(0);
  });

  it('records again without repeating the step when only recording failed', async () => {
    serveThread(suggestion({ kind: 'start_draft' }));
    const started = recordTo('post', `${API}/projects/${PROJECT_ID}/runs`, () =>
      HttpResponse.json(makeRun({ status: 'created' }), { status: 202 }),
    );
    let attempts = 0;
    const recorded = recordTo('put', STATUS_URL, () => {
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json(errorBody('SUGGESTION_CHANGED', 'This suggestion changed.'), {
            status: 409,
          })
        : HttpResponse.json(suggestion({ status: 'accepted', revision: 2 }));
    });
    renderApp(CHAT);

    await userEvent.click(await (await shownCard()).findByRole('button', { name: 'Start run' }));
    expect(await (await shownCard()).findByRole('alert')).toHaveTextContent(
      'The step was taken, but marking this suggestion as done failed. This suggestion changed.',
    );
    await userEvent.click(card().getByRole('button', { name: 'Mark as done' }));

    await waitFor(() => {
      expect(recorded).toHaveLength(2);
    });
    expect(started).toHaveLength(1);
  });

  it('shows a viewer the suggestion without any button', async () => {
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({ ...PROJECT, roles: ['viewer'] }),
      ),
    );
    serveThread(suggestion({ kind: 'start_draft' }));
    renderApp(CHAT);

    expect(
      await (await shownCard()).findByText('An editor or approver can take this step.'),
    ).toBeVisible();
    expect(card().queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('Reply progress', () => {
  it('lists what the reply looked up while it works, and nothing once it is done', async () => {
    const run = makeRun({
      id: '019a3a5e-0000-7000-8000-0000000000f2',
      mode: 'reply',
      stage: 'reply',
      status: 'running',
      lookups: [
        { tool: 'get_story', found: 1, refused: false },
        { tool: 'list_open_decisions', found: 2, refused: false },
        { tool: 'lookup_source', found: 0, refused: true },
      ],
    });
    let finished = false;
    server.use(
      http.get(MESSAGES_URL, () =>
        HttpResponse.json<Conversation>({
          messages: [],
          next_cursor: null,
          active_run: finished ? null : { id: run.id, mode: 'reply', status: 'running' },
        }),
      ),
      http.get(`${API}/runs/${run.id}`, () =>
        HttpResponse.json(finished ? { ...run, status: 'completed' } : run),
      ),
      http.post(`${API}/runs/${run.id}/advance`, () => {
        finished = true;
        return HttpResponse.json({ ...run, status: 'completed' });
      }),
    );
    renderApp(CHAT);

    const lines = within(await screen.findByRole('list', { name: 'What the agent looked up' }));

    expect(lines.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Looked up a backlog item',
      'Checked the open decisions',
    ]);
    await waitFor(() => {
      expect(
        screen.queryByRole('list', { name: 'What the agent looked up' }),
      ).not.toBeInTheDocument();
    });
  });
});
