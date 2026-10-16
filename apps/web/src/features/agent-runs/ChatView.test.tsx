import type { components } from '@scopesteps/api-client';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BACKLOG,
  BRIEF,
  BRIEF_BLOCKS,
  CANCEL_ANSWER,
  CANCEL_QUESTION,
  errorBody,
  LENGTH_QUESTION,
  makeRun,
  PROJECT,
  PROJECT_ID,
  REVIEWER,
  REVIEWER_ID,
  RUN_ID,
  TRANSCRIPT,
  VERSION_ID,
  VIEWER,
} from '@/test/fixtures';
import { API, MESSAGES_URL, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { Message, Question, Run } from './types';

type Conversation = components['schemas']['ConversationResponse'];

const CHAT = `/projects/${PROJECT_ID}/chat`;
const RUN_URL = `${API}/runs/${RUN_ID}`;
const REPLY_RUN_ID = '019a3a5e-0000-7000-8000-0000000000f2';
const REPLY_RUN_URL = `${API}/runs/${REPLY_RUN_ID}`;
const BASELINE_ID = '019a3a5e-0000-7000-8000-0000000000e9';
const OUTBOX_KEY = `scopesteps:outbox:${PROJECT_ID}`;
const AT = '2026-10-15T09:00:00Z';
const QUESTION_TEXT = 'How late may a user cancel a booking?';

let messageCount = 0;
function message(overrides: Partial<Message>): Message {
  messageCount += 1;
  return {
    id: `019a3a5e-0000-7000-8000-${String(messageCount).padStart(12, '0')}`,
    author: null,
    claims: [],
    created_at: AT,
    event: null,
    change_request_id: null,
    baseline_version: null,
    kind: 'message',
    question: null,
    question_id: null,
    role: 'user',
    run_id: null,
    text: '',
    ...overrides,
  };
}

function userMessage(text: string, kind: Message['kind'] = 'message'): Message {
  return message({
    kind,
    text,
    author: { user_id: REVIEWER_ID, display_name: REVIEWER.display_name },
  });
}

function questionState(question: Question): NonNullable<Message['question']> {
  return {
    id: question.id,
    run_id: RUN_ID,
    round: question.round,
    status: question.status,
    subject: question.subject,
    why_it_matters: question.why_it_matters,
    answer: question.answer,
    answered_at: question.answered_at,
    answered_by: question.answered_by,
  };
}

function questionMessage(question: Question): Message {
  return message({
    kind: 'question',
    role: 'agent',
    run_id: RUN_ID,
    question_id: question.id,
    text: question.text,
    question: questionState(question),
  });
}

const REPLY = message({
  kind: 'reply',
  role: 'agent',
  run_id: REPLY_RUN_ID,
  text: 'A booking can last up to 4 hours.',
  claims: [
    {
      basis: 'cited',
      text: 'A booking can last up to 4 hours.',
      citations: [
        {
          quote: 'A booking can last up to 4 hours.',
          question_id: null,
          evidence: {
            source_version_id: BRIEF.id,
            block_id: BRIEF_BLOCKS[1]?.id ?? '',
            quote: 'A booking can last up to 4 hours.',
            relationship: 'supporting',
          },
        },
      ],
    },
    { basis: 'agent', text: 'Rooms may differ by building.', citations: [] },
  ],
});

const WAITING = makeRun({
  status: 'waiting_for_input',
  revision: 3,
  questions: [CANCEL_QUESTION, LENGTH_QUESTION],
});
const ANSWERED_CANCEL: Question = {
  ...CANCEL_QUESTION,
  status: 'answered',
  answer: CANCEL_ANSWER,
  answered_by: REVIEWER_ID,
  answered_at: AT,
};
const READY = makeRun({
  status: 'ready_for_review',
  stage: 'draft',
  revision: 9,
  candidate_version_id: VERSION_ID,
  questions: [ANSWERED_CANCEL],
});

function page(overrides: Partial<Conversation>): Conversation {
  return { messages: [], next_cursor: null, active_run: null, ...overrides };
}

/** Serves the conversation from `current`, newest first as the API does. */
function serveConversation(initial: Conversation) {
  const state = { current: initial, requests: [] as URL[] };
  server.use(
    http.get(MESSAGES_URL, ({ request }) => {
      state.requests.push(new URL(request.url));
      return HttpResponse.json(state.current);
    }),
  );
  return state;
}

/** Newest first, as the API pages it. */
function newestFirst(...thread: Message[]): Message[] {
  return [...thread].reverse();
}

interface Sent {
  key: string | null;
  body: unknown;
}

/** Serves one endpoint from a queue of replies and records what was sent to it. */
function record(
  method: 'get' | 'post',
  url: string,
  ...replies: (Run | Response | Record<string, unknown> | (() => Response))[]
) {
  const sent: Sent[] = [];
  server.use(
    http[method](url, async ({ request }) => {
      sent.push({
        key: request.headers.get('Idempotency-Key'),
        body: method === 'post' ? await request.json().catch(() => null) : null,
      });
      const reply = replies[Math.min(sent.length, replies.length) - 1];
      if (typeof reply === 'function') {
        return reply();
      }
      return reply instanceof Response ? reply.clone() : HttpResponse.json(reply);
    }),
  );
  return sent;
}

function withProject(status: Partial<(typeof PROJECT)['status']>, maxChars = 2000) {
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        status: { ...PROJECT.status, ...status },
        limits: { ...PROJECT.limits, conversation: { max_message_chars: maxChars } },
      }),
    ),
  );
}

function composer() {
  return screen.getByRole('textbox', { name: 'Message ScopeSteps' });
}

function question(text: string) {
  return within(screen.getByRole('article', { name: text }));
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  server.use(...projectHandlers());
});

describe('ChatView', () => {
  it('moves to the setup steps when a failed run offers a new one', async () => {
    serveConversation(
      page({
        messages: newestFirst(
          message({
            kind: 'event',
            role: 'system',
            event: 'run.failed',
            run_id: RUN_ID,
            text: 'Model provider rejected the request (HTTP 400)',
          }),
        ),
      }),
    );
    renderApp(CHAT);

    await userEvent.click(await screen.findByRole('button', { name: 'Start a new run' }));

    const steps = await screen.findByRole('region', { name: 'New chat for Study Room Booking' });
    await waitFor(() => {
      expect(steps).toHaveFocus();
    });
    expect(within(steps).getByRole('button', { name: 'Start run' })).toBeVisible();
  });

  it('starts the first run from the new chat and shows what the agent asks, with its evidence', async () => {
    const convo = serveConversation(page({}));
    const created = record('post', `${API}/projects/${PROJECT_ID}/runs`, () => {
      convo.current = page({
        messages: newestFirst(
          message({
            kind: 'event',
            role: 'system',
            event: 'run.started',
            run_id: RUN_ID,
            text: 'Started a run on 2 source versions.',
          }),
          questionMessage(CANCEL_QUESTION),
        ),
        active_run: { id: RUN_ID, mode: 'initial', status: 'waiting_for_input' },
      });
      return HttpResponse.json(makeRun());
    });
    record('post', `${RUN_URL}/advance`, WAITING);
    record('get', RUN_URL, WAITING);
    const router = renderApp(CHAT);

    expect(
      await screen.findByRole('heading', { name: 'New chat for Study Room Booking' }),
    ).toBeInTheDocument();
    await screen.findByText('2 sources added · 60 of 6,000 words');
    fireEvent.click(screen.getByRole('button', { name: 'Start run' }));

    const card = within(await screen.findByRole('article', { name: QUESTION_TEXT }));
    expect(created).toHaveLength(1);
    expect(created[0]?.body).toEqual({
      mode: 'initial',
      source_version_ids: [BRIEF.id, TRANSCRIPT.id],
    });
    expect(screen.getByText('Started a run on 2 source versions.')).toBeInTheDocument();
    expect(card.getByText('Needs an answer')).toBeInTheDocument();
    await userEvent.click(await card.findByRole('button', { name: 'Brief ¶2' }));

    const sheet = within(screen.getByRole('dialog', { name: 'Evidence' }));
    expect(await sheet.findByText(/A booking can last up to 4 hours\./)).toBeInTheDocument();
    expect(router.state.location.search).toContain(
      `evidence=question%3A${RUN_ID}%3A${CANCEL_QUESTION.id}`,
    );
  });

  it('sends a message with Enter once, with a key, and shows the cited reply as it arrives', async () => {
    const convo = serveConversation(page({}));
    const sent = record('post', MESSAGES_URL, () => {
      convo.current = page({
        messages: [userMessage('How long can a booking last?')],
        active_run: { id: REPLY_RUN_ID, mode: 'reply', status: 'created' },
      });
      return HttpResponse.json(
        {
          message: userMessage('How long can a booking last?'),
          run: makeRun({ id: REPLY_RUN_ID, mode: 'reply' }),
        },
        { status: 202 },
      );
    });
    const advanced = record('post', `${REPLY_RUN_URL}/advance`, () => {
      convo.current = page({
        messages: newestFirst(userMessage('How long can a booking last?'), REPLY),
      });
      return HttpResponse.json(
        makeRun({ id: REPLY_RUN_ID, mode: 'reply', status: 'completed', revision: 2 }),
      );
    });
    const router = renderApp(CHAT);
    await screen.findByRole('heading', { name: 'New chat for Study Room Booking' });
    await waitFor(() => {
      expect(composer()).toBeEnabled();
    });

    await userEvent.type(composer(), 'How long can a booking last?{Enter}');

    expect(
      await screen.findByRole('article', { name: 'Message from Local Reviewer' }),
    ).toHaveTextContent('How long can a booking last?');
    expect(await screen.findByText('Rooms may differ by building.')).toBeInTheDocument();
    expect(screen.getByText('Agent’s own words · no evidence')).toBeInTheDocument();
    expect(sent).toHaveLength(1);
    expect(sent[0]?.body).toEqual({ kind: 'message', text: 'How long can a booking last?' });
    expect(sent[0]?.key).toBeTruthy();
    expect(advanced).toEqual([{ key: `advance-${REPLY_RUN_ID}-1`, body: null }]);
    expect(composer()).toHaveValue('');

    await userEvent.click(
      await screen.findByRole('button', { name: /evidence for: A booking can last up to 4 hours/ }),
    );
    const sheet = within(screen.getByRole('dialog', { name: 'Evidence' }));
    expect(sheet.getByText('What the agent said')).toBeInTheDocument();
    expect(router.state.location.search).toContain(`evidence=reply%3A${REPLY.id}%3A0`);
  });

  it('adds a line with Shift+Enter and shows the API’s length limit as it is approached', async () => {
    withProject({}, 20);
    serveConversation(page({ messages: [userMessage('Earlier')] }));
    renderApp(CHAT);
    await screen.findByRole('article', { name: 'Message from Local Reviewer' });
    await waitFor(() => {
      expect(composer()).toBeEnabled();
    });

    await userEvent.type(composer(), 'Line one{Shift>}{Enter}{/Shift}two');
    expect(composer()).toHaveValue('Line one\ntwo');
    expect(screen.queryByText(/\/ 20/)).not.toBeInTheDocument();
    expect(screen.getByText(/Up to 20 characters/)).toBeInTheDocument();

    await userEvent.type(composer(), ' three');
    expect(screen.getByText('18 / 20')).toBeInTheDocument();
    await userEvent.type(composer(), ' four');
    expect(screen.getByRole('alert')).toHaveTextContent('This is 3 characters over the limit.');
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('answers the question chosen on its card and skips another, saying which is answered', async () => {
    serveConversation(
      page({
        messages: newestFirst(questionMessage(CANCEL_QUESTION), questionMessage(LENGTH_QUESTION)),
        active_run: { id: RUN_ID, mode: 'initial', status: 'waiting_for_input' },
      }),
    );
    record('get', RUN_URL, WAITING);
    const answered: Run = {
      ...WAITING,
      revision: 4,
      questions: [ANSWERED_CANCEL, LENGTH_QUESTION],
    };
    const replies = record('post', `${RUN_URL}/answers`, answered, {
      ...answered,
      revision: 5,
      questions: [
        ANSWERED_CANCEL,
        { ...LENGTH_QUESTION, status: 'skipped', answered_by: REVIEWER_ID },
      ],
    });
    renderApp(CHAT);

    await screen.findByRole('article', { name: QUESTION_TEXT });
    await userEvent.click(question(QUESTION_TEXT).getByRole('button', { name: 'Answer' }));
    expect(composer()).toHaveFocus();
    expect(screen.getByText(`Answering: ${QUESTION_TEXT}`)).toBeVisible();
    await userEvent.type(composer(), `${CANCEL_ANSWER}{Enter}`);

    expect(await question(QUESTION_TEXT).findByText(CANCEL_ANSWER)).toBeInTheDocument();
    expect(screen.queryByText(/^Answering:/)).not.toBeInTheDocument();

    await userEvent.click(
      question('Is the maximum booking length four hours or three hours?').getByRole('button', {
        name: 'Skip',
      }),
    );
    await waitFor(() => {
      expect(replies).toHaveLength(2);
    });
    expect(replies.map((reply) => reply.body)).toEqual([
      { question_id: CANCEL_QUESTION.id, answer: CANCEL_ANSWER, skip: false },
      { question_id: LENGTH_QUESTION.id, skip: true },
    ]);
    expect(new Set(replies.map((reply) => reply.key)).size).toBe(2);
  });

  it('changes an answer until its draft is decided, against the run’s revision', async () => {
    withProject({ state: 'draft_in_progress', open_version_id: VERSION_ID });
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
        HttpResponse.json(BACKLOG),
      ),
    );
    serveConversation(
      page({
        messages: newestFirst(
          questionMessage(ANSWERED_CANCEL),
          message({
            kind: 'answer',
            role: 'user',
            run_id: RUN_ID,
            text: CANCEL_ANSWER,
            question_id: CANCEL_QUESTION.id,
            question: questionState(ANSWERED_CANCEL),
            author: { user_id: REVIEWER_ID, display_name: REVIEWER.display_name },
          }),
        ),
      }),
    );
    record('get', RUN_URL, READY);
    const replies = record('post', `${RUN_URL}/answers`, { ...READY, revision: 10 });
    renderApp(CHAT);

    const decision = await screen.findByRole('article', { name: /Decision · Cancellation/ });
    expect(within(decision).getByText('Answered')).toBeInTheDocument();
    await screen.findByRole('article', { name: QUESTION_TEXT });
    await userEvent.click(question(QUESTION_TEXT).getByRole('button', { name: 'Change answer' }));
    expect(screen.getByText(`Changing the answer to: ${QUESTION_TEXT}`)).toBeVisible();
    await userEvent.type(composer(), 'Up to two hours before.{Enter}');

    await waitFor(() => {
      expect(replies).toHaveLength(1);
    });
    expect(replies[0]?.body).toEqual({
      question_id: CANCEL_QUESTION.id,
      answer: 'Up to two hours before.',
      skip: false,
      expected_revision: 9,
    });
  });

  it('refreshes the project once a run is ready, so a skipped question stays changeable', async () => {
    const LENGTH_TEXT = LENGTH_QUESTION.text;
    let status: Partial<(typeof PROJECT)['status']> = { state: 'no_baseline' };
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({ ...PROJECT, status: { ...PROJECT.status, ...status } }),
      ),
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
        HttpResponse.json(BACKLOG),
      ),
    );
    const waiting = makeRun({
      status: 'waiting_for_input',
      revision: 3,
      questions: [LENGTH_QUESTION],
    });
    const skipped: Question = { ...LENGTH_QUESTION, status: 'skipped', answered_by: REVIEWER_ID };
    serveConversation(
      page({
        messages: [questionMessage(LENGTH_QUESTION)],
        active_run: { id: RUN_ID, mode: 'initial', status: 'waiting_for_input' },
      }),
    );
    record('get', RUN_URL, waiting);
    record('post', `${RUN_URL}/answers`, {
      ...waiting,
      status: 'running',
      revision: 4,
      questions: [skipped],
    });
    record('post', `${RUN_URL}/advance`, () => {
      // The server saved the draft in the same step that made the run ready.
      status = { state: 'draft_in_progress', open_version_id: VERSION_ID };
      return HttpResponse.json({
        ...READY,
        revision: 5,
        questions: [skipped],
      });
    });
    renderApp(`${CHAT}?run=${RUN_ID}`);

    await screen.findByRole('article', { name: LENGTH_TEXT });
    await userEvent.click(await question(LENGTH_TEXT).findByRole('button', { name: 'Skip' }));

    expect(await question(LENGTH_TEXT).findByRole('button', { name: 'Answer now' })).toBeVisible();
    expect(screen.queryByText(/^Locked:/)).not.toBeInTheDocument();
    expect(await screen.findByText('Draft in progress')).toBeInTheDocument();
    expect(screen.queryByText('No baseline yet')).not.toBeInTheDocument();
  });

  it('shows a question skipped here and answered on the backlog as answered', async () => {
    withProject({ state: 'draft_in_progress', open_version_id: VERSION_ID });
    const skipped: Question = { ...CANCEL_QUESTION, status: 'skipped', answered_by: REVIEWER_ID };
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
        HttpResponse.json({
          ...BACKLOG,
          decisions: BACKLOG.decisions.map((decision, index) =>
            index === 0
              ? {
                  ...decision,
                  question_id: CANCEL_QUESTION.id,
                  status: 'answered',
                  answer: 'Up to an hour before.',
                  decided_by: REVIEWER_ID,
                }
              : decision,
          ),
        }),
      ),
    );
    serveConversation(page({ messages: [questionMessage(skipped)] }));
    record('get', RUN_URL, { ...READY, questions: [skipped] });
    renderApp(CHAT);

    await screen.findByRole('article', { name: QUESTION_TEXT });
    expect(await question(QUESTION_TEXT).findByText('Answered on the backlog')).toBeVisible();
    expect(question(QUESTION_TEXT).getByText('Up to an hour before.')).toBeVisible();
    expect(screen.queryByText(/Skipped · still open/)).not.toBeInTheDocument();
    expect(question(QUESTION_TEXT).queryByRole('button', { name: 'Answer now' })).toBeNull();
    await expectNoAccessibilityViolations();
  });

  it('locks an answer once the version that used it is approved', async () => {
    withProject({ state: 'baseline', baseline_version: 1, baseline_version_id: VERSION_ID });
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
        HttpResponse.json({ ...BACKLOG, state: 'approved' }),
      ),
    );
    serveConversation(page({ messages: [questionMessage(ANSWERED_CANCEL)] }));
    record('get', RUN_URL, READY);
    renderApp(CHAT);

    await screen.findByRole('article', { name: QUESTION_TEXT });
    expect(
      question(QUESTION_TEXT).getByText('Locked: the version that uses this answer is approved.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Change answer' })).not.toBeInTheDocument();
  });

  it('sends a change request against the baseline as the requester saw it', async () => {
    withProject({ state: 'baseline', baseline_version: 1, baseline_version_id: BASELINE_ID });
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${BASELINE_ID}`, () =>
        HttpResponse.json({ ...BACKLOG, id: BASELINE_ID, state: 'approved' }),
      ),
    );
    serveConversation(page({ messages: [userMessage('Earlier')] }));
    const sent = record(
      'post',
      MESSAGES_URL,
      HttpResponse.json(
        {
          message: userMessage('Add a waitlist', 'change_request'),
          run: makeRun({ id: REPLY_RUN_ID, mode: 'change', status: 'completed' }),
        },
        { status: 202 },
      ),
    );
    renderApp(CHAT);
    const toggle = await screen.findByRole('button', { name: 'Change request' });
    await waitFor(() => {
      expect(toggle).toBeEnabled();
    });

    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    await userEvent.type(composer(), 'Add a waitlist{Enter}');

    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]?.body).toEqual({
      kind: 'change_request',
      text: 'Add a waitlist',
      base_version_id: BASELINE_ID,
      base_content_hash: BACKLOG.content_hash,
    });
  });

  it.each([
    [{ state: 'no_baseline' as const }, 'Change requests need an approved baseline to change.'],
    [
      {
        state: 'candidate_in_review' as const,
        baseline_version: 1,
        baseline_version_id: BASELINE_ID,
        open_version_id: VERSION_ID,
      },
      'A change is in review. Approve or reject it before requesting another.',
    ],
  ])('explains why a change request is unavailable (%o)', async (status, reason) => {
    withProject(status);
    serveConversation(page({ messages: [userMessage('Earlier')] }));
    renderApp(CHAT);

    const toggle = await screen.findByRole('button', { name: 'Change request' });
    expect(await screen.findByText(reason)).toBeInTheDocument();
    expect(toggle).toBeDisabled();
    expect(toggle).toHaveAccessibleDescription(reason);
  });

  it('shows the agent working and stops it once with Stop in place of Send', async () => {
    serveConversation(
      page({
        messages: [userMessage('How long can a booking last?')],
        active_run: { id: REPLY_RUN_ID, mode: 'reply', status: 'running' },
      }),
    );
    const running = makeRun({ id: REPLY_RUN_ID, mode: 'reply', status: 'running', revision: 2 });
    record('get', REPLY_RUN_URL, running);
    // The step is slow: the run stays running while the page is looked at.
    server.use(http.post(`${REPLY_RUN_URL}/advance`, () => new Promise<Response>(() => undefined)));
    const cancelled = record('post', `${REPLY_RUN_URL}/cancel`, {
      ...running,
      status: 'cancelled',
    });
    renderApp(CHAT);

    expect(
      await screen.findByText('Writing a reply from your sources and answers…'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument();
    expect(composer()).toBeDisabled();
    const stop = screen.getByRole('button', { name: 'Stop the agent' });
    fireEvent.click(stop);
    fireEvent.click(stop);

    await waitFor(() => {
      expect(cancelled).toHaveLength(1);
    });
    expect(cancelled[0]?.key).toBe(`cancel-${REPLY_RUN_ID}`);
  });

  it('keeps a message that failed to send, with why, and retries it with the same key', async () => {
    const convo = serveConversation(page({ messages: [userMessage('Earlier')] }));
    const sent = record(
      'post',
      MESSAGES_URL,
      HttpResponse.json(errorBody('AGENT_BUSY', 'The agent is busy.', true), { status: 409 }),
      () => {
        convo.current = page({
          messages: newestFirst(userMessage('Earlier'), userMessage('Is parking included?')),
        });
        return HttpResponse.json(
          {
            message: userMessage('Is parking included?'),
            run: makeRun({ id: REPLY_RUN_ID, mode: 'reply', status: 'completed' }),
          },
          { status: 202 },
        );
      },
    );
    renderApp(CHAT);
    await screen.findByRole('article', { name: 'Message from Local Reviewer' });
    await waitFor(() => {
      expect(composer()).toBeEnabled();
    });

    await userEvent.type(composer(), 'Is parking included?{Enter}');

    expect(
      await screen.findByText(
        'Not sent. The agent is busy with other work. Try again once it has finished.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Is parking included?')).toBeInTheDocument();
    expect(window.sessionStorage.getItem(OUTBOX_KEY)).toContain('Is parking included?');

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(screen.queryByText(/^Not sent\./)).not.toBeInTheDocument();
    });
    expect(screen.getAllByText('Is parking included?')).toHaveLength(1);
    expect(sent).toHaveLength(2);
    expect(sent[1]?.key).toBe(sent[0]?.key);
    expect(window.sessionStorage.getItem(OUTBOX_KEY)).toBeNull();
  });

  it('brings back a message whose send was not confirmed before a reload', async () => {
    window.sessionStorage.setItem(
      OUTBOX_KEY,
      JSON.stringify([
        {
          localId: 'local-1',
          idempotencyKey: 'key-1',
          text: 'Unconfirmed message',
          kind: 'message',
          base: null,
          status: 'sending',
          error: null,
        },
      ]),
    );
    serveConversation(page({ messages: [userMessage('Earlier')] }));
    renderApp(CHAT);

    expect(await screen.findByText('Unconfirmed message')).toBeInTheDocument();
    expect(
      screen.getByText('Not sent. The page was reloaded before the message was confirmed.'),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.queryByText('Unconfirmed message')).not.toBeInTheDocument();
  });

  it('loads older messages on demand, above the newer ones', async () => {
    const older = userMessage('The oldest question');
    const convo = serveConversation(page({ messages: [userMessage('Newest')], next_cursor: 'c1' }));
    server.use(
      http.get(MESSAGES_URL, ({ request }) => {
        convo.requests.push(new URL(request.url));
        return new URL(request.url).searchParams.get('cursor') === 'c1'
          ? HttpResponse.json(page({ messages: [older] }))
          : HttpResponse.json(convo.current);
      }),
    );
    renderApp(CHAT);

    await userEvent.click(await screen.findByRole('button', { name: 'Load older messages' }));

    const bubbles = await screen.findAllByRole('article', { name: 'Message from Local Reviewer' });
    expect(bubbles.map((bubble) => bubble.textContent)).toEqual([
      expect.stringContaining('The oldest question'),
      expect.stringContaining('Newest'),
    ]);
    expect(screen.queryByRole('button', { name: 'Load older messages' })).not.toBeInTheDocument();
  });

  it('shows the events, failures and decisions of runs as the server worded them', async () => {
    serveConversation(
      page({
        messages: newestFirst(
          message({
            kind: 'event',
            role: 'system',
            event: 'run.ready_for_review',
            run_id: RUN_ID,
            text: 'The draft backlog is ready for review.',
          }),
          message({
            kind: 'skip',
            role: 'user',
            run_id: RUN_ID,
            question_id: LENGTH_QUESTION.id,
            question: { ...questionState(LENGTH_QUESTION), status: 'skipped' },
            author: { user_id: REVIEWER_ID, display_name: REVIEWER.display_name },
          }),
          message({
            kind: 'event',
            role: 'system',
            event: 'reply.failed',
            run_id: REPLY_RUN_ID,
            text: 'The provider timed out.',
          }),
        ),
      }),
    );
    record('get', RUN_URL, READY);
    renderApp(CHAT);

    expect(await screen.findByText('The draft backlog is ready for review.')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Open backlog' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`,
    );
    const skipped = screen.getByRole('article', { name: /Decision · Maximum booking length/ });
    expect(within(skipped).getByText('Skipped')).toBeInTheDocument();
    expect(screen.getByText(/The provider timed out\./)).toBeInTheDocument();
  });

  it('gives a viewer the thread with a disabled composer that says why', async () => {
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));
    serveConversation(
      page({
        messages: newestFirst(userMessage('Earlier'), questionMessage(CANCEL_QUESTION)),
        active_run: { id: RUN_ID, mode: 'initial', status: 'waiting_for_input' },
      }),
    );
    record('get', RUN_URL, WAITING);
    const advanced = record('post', `${RUN_URL}/advance`, WAITING);
    renderApp(CHAT);

    await screen.findByRole('article', { name: QUESTION_TEXT });
    await waitFor(() => {
      expect(composer()).toHaveAttribute(
        'placeholder',
        'View-only access. An editor can message the agent.',
      );
    });
    expect(composer()).toBeDisabled();
    expect(
      screen.getByText(
        'You have view-only access to this project, so you cannot message the agent.',
      ),
    ).toBeInTheDocument();
    for (const name of ['Answer', 'Skip', 'Stop the run', 'Change request', 'Add a source']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(advanced).toHaveLength(0);
  });

  it('has no example, scripted or demo wording', async () => {
    serveConversation(page({ messages: [userMessage('Earlier'), REPLY] }));
    renderApp(CHAT);
    await screen.findByText('Rooms may differ by building.');

    expect(screen.queryByRole('button', { name: /example/i })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/demo|scripted|use example/i);
  });

  it('warns before a new run replaces a draft that people have edited', async () => {
    withProject({ state: 'draft_in_progress', open_version_id: VERSION_ID });
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
        HttpResponse.json({ ...BACKLOG, revision: 3 }),
      ),
    );
    const created = record('post', `${API}/projects/${PROJECT_ID}/runs`, makeRun());
    record('post', `${RUN_URL}/advance`, WAITING);
    record('get', RUN_URL, WAITING);
    renderApp(CHAT);
    const start = await screen.findByRole('button', { name: 'Start run' });
    await waitFor(() => {
      expect(start).toBeEnabled();
    });

    await userEvent.click(start);
    const dialog = within(screen.getByRole('dialog', { name: 'Start a new run?' }));
    await userEvent.click(dialog.getByRole('button', { name: 'Cancel' }));
    expect(created).toHaveLength(0);
    await userEvent.click(start);
    await userEvent.click(screen.getByRole('button', { name: 'Start a new run anyway' }));

    await waitFor(() => {
      expect(created).toHaveLength(1);
    });
  });

  it('has no accessibility violations as a new chat', async () => {
    renderApp(CHAT);
    await screen.findByText('2 sources added · 60 of 6,000 words');
    await expectNoAccessibilityViolations();
  });

  it('has no accessibility violations with a reply, questions and the composer in use', async () => {
    serveConversation(
      page({
        messages: newestFirst(userMessage('Earlier'), REPLY, questionMessage(CANCEL_QUESTION)),
        active_run: { id: RUN_ID, mode: 'initial', status: 'waiting_for_input' },
      }),
    );
    record('get', RUN_URL, WAITING);
    renderApp(CHAT);
    await userEvent.click(
      within(await screen.findByRole('article', { name: QUESTION_TEXT })).getByRole('button', {
        name: 'Answer',
      }),
    );
    await screen.findAllByRole('button', { name: /Brief ¶2/ });
    await expectNoAccessibilityViolations();
  });
});
