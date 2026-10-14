import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BRIEF,
  BRIEF_BLOCKS,
  CANCEL_ANSWER,
  CANCEL_QUESTION,
  errorBody,
  LENGTH_QUESTION,
  makeRun,
  PROJECT_ID,
  REVIEWER_ID,
  RUN_ID,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
  VERSION_ID,
  VIEWER,
} from '@/test/fixtures';
import { API, projectHandlers, SOURCES_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { Run } from './types';

const CHAT = `/projects/${PROJECT_ID}/chat`;
const RUN_URL = `${API}/runs/${RUN_ID}`;
const LAST_RUN_KEY = `scopesteps:last-run:${PROJECT_ID}`;
const WAITING = makeRun({
  status: 'waiting_for_input',
  revision: 3,
  questions: [CANCEL_QUESTION, LENGTH_QUESTION],
});
const READY = makeRun({
  status: 'ready_for_review',
  stage: 'draft',
  revision: 9,
  candidate_version_id: VERSION_ID,
});

interface Sent {
  key: string | null;
  body: unknown;
}

/** Serves one endpoint from a queue of replies and records what was sent to it. */
function record(
  method: 'get' | 'post',
  url: string,
  ...replies: (Run | Response | (() => Promise<Response>))[]
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

function question(text: string) {
  return within(screen.getByRole('article', { name: text }));
}

function composer() {
  return screen.getByRole('textbox', { name: 'Message ScopeSteps' });
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('ChatView', () => {
  it('starts one run on the stored sources and shows what the agent asks, with its evidence', async () => {
    const created = record('post', `${API}/projects/${PROJECT_ID}/runs`, makeRun());
    const advanced = record('post', `${RUN_URL}/advance`, WAITING);
    record('get', RUN_URL, makeRun());
    const router = renderApp(CHAT);

    expect(
      await screen.findByRole('heading', { name: 'New chat for Study Room Booking' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('2 sources added · 60 of 6,000 words')).toBeInTheDocument();
    const start = screen.getByRole('button', { name: 'Start run' });
    fireEvent.click(start);
    fireEvent.click(start);

    const cancel = await screen.findByRole('article', {
      name: 'How late may a user cancel a booking?',
    });
    expect(router.state.location.search).toBe(`?run=${RUN_ID}`);
    expect(window.localStorage.getItem(LAST_RUN_KEY)).toBe(RUN_ID);
    expect(created).toHaveLength(1);
    expect(created[0]?.body).toEqual({
      mode: 'initial',
      source_version_ids: [BRIEF.id, TRANSCRIPT.id],
    });
    expect(created[0]?.key).toBeTruthy();
    expect(advanced).toEqual([{ key: `advance-${RUN_ID}-1`, body: null }]);
    expect(screen.getByText('Run started on brief.md v1 and transcript.md v1')).toBeInTheDocument();

    const card = within(cancel);
    expect(card.getByText('Needs an answer')).toBeInTheDocument();
    expect(card.getByText('Cancellation and no-shows')).toBeInTheDocument();
    expect(card.getByText(/The sources leave the cancellation rule open\./)).toBeInTheDocument();
    await userEvent.click(await card.findByRole('button', { name: 'Brief ¶2' }));

    const sheet = within(screen.getByRole('dialog', { name: 'Evidence' }));
    expect(sheet.getByRole('heading', { name: 'Evidence' })).toHaveFocus();
    expect(await sheet.findByText(/A booking can last up to 4 hours\./)).toBeInTheDocument();
    expect(sheet.getByText('brief.md · Project brief v1 · paragraph 2')).toBeInTheDocument();
    expect(router.state.location.search).toContain(`evidence=question%3A${CANCEL_QUESTION.id}`);
  });

  it('answers in the composer and skips, once each, then resumes to the finished draft', async () => {
    record('get', RUN_URL, WAITING);
    const answered: Run = {
      ...WAITING,
      revision: 4,
      questions: [
        {
          ...CANCEL_QUESTION,
          status: 'answered',
          answer: CANCEL_ANSWER,
          answered_by: REVIEWER_ID,
          answered_at: '2026-10-13T10:00:00Z',
        },
        LENGTH_QUESTION,
      ],
    };
    const resumed: Run = {
      ...answered,
      status: 'running',
      stage: 'draft',
      revision: 5,
      questions: [
        answered.questions[0] ?? CANCEL_QUESTION,
        { ...LENGTH_QUESTION, status: 'skipped', answered_by: REVIEWER_ID },
      ],
    };
    const replies = record('post', `${RUN_URL}/answers`, answered, resumed);
    const advanced = record('post', `${RUN_URL}/advance`, {
      ...READY,
      questions: resumed.questions,
    });

    renderApp(`${CHAT}?run=${RUN_ID}`);
    await screen.findByRole('article', { name: 'How late may a user cancel a booking?' });
    expect(composer()).toBeDisabled();
    expect(composer()).toHaveAttribute('placeholder', 'Choose Answer on a question to reply');

    await userEvent.click(
      question('How late may a user cancel a booking?').getByRole('button', { name: 'Answer' }),
    );
    expect(composer()).toHaveFocus();
    expect(screen.getByText('Answering: How late may a user cancel a booking?')).toBeVisible();
    const send = screen.getByRole('button', { name: 'Send' });
    expect(send).toBeDisabled();
    fireEvent.change(composer(), { target: { value: `  ${CANCEL_ANSWER}  ` } });
    fireEvent.click(send);
    fireEvent.click(send);

    const cancellation = question('How late may a user cancel a booking?');
    expect(await cancellation.findByText(CANCEL_ANSWER)).toBeInTheDocument();
    expect(cancellation.getByText('Answered by Local Reviewer')).toBeInTheDocument();
    expect(composer()).toHaveValue('');
    expect(screen.queryByText(/^Answering:/)).not.toBeInTheDocument();
    expect(advanced).toHaveLength(0);

    await userEvent.click(
      question('Is the maximum booking length four hours or three hours?').getByRole('button', {
        name: 'Skip',
      }),
    );

    expect(await screen.findByText('Draft ready')).toBeInTheDocument();
    const length = question('Is the maximum booking length four hours or three hours?');
    expect(length.getByText('Skipped · still open')).toBeInTheDocument();
    expect(length.getByText(/No answer was assumed/)).toBeInTheDocument();
    expect(screen.getByText('All questions handled. Drafting the backlog.')).toBeInTheDocument();
    expect(replies.map((reply) => reply.body)).toEqual([
      { question_id: CANCEL_QUESTION.id, answer: CANCEL_ANSWER, skip: false },
      { question_id: LENGTH_QUESTION.id, skip: true },
    ]);
    expect(new Set(replies.map((reply) => reply.key)).size).toBe(2);
    expect(advanced).toEqual([{ key: `advance-${RUN_ID}-5`, body: null }]);
    expect(screen.getByRole('link', { name: 'Open backlog' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`,
    );
  });

  it('answers from the keyboard alone: Answer, type, Shift+Enter for a line, Enter to send', async () => {
    record('get', RUN_URL, WAITING);
    const replies = record('post', `${RUN_URL}/answers`, {
      ...WAITING,
      revision: 4,
      questions: [{ ...CANCEL_QUESTION, status: 'answered', answer: 'One\nTwo' }, LENGTH_QUESTION],
    });
    renderApp(`${CHAT}?run=${RUN_ID}`);
    await screen.findByRole('article', { name: 'How late may a user cancel a booking?' });

    question('How late may a user cancel a booking?')
      .getByRole('button', { name: 'Answer' })
      .focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('One{Shift>}{Enter}{/Shift}Two{Enter}');

    await waitFor(() => {
      expect(replies).toHaveLength(1);
    });
    expect(replies[0]?.body).toEqual({
      question_id: CANCEL_QUESTION.id,
      answer: 'One\nTwo',
      skip: false,
    });
  });

  it('keeps the typed answer and says so when saving it fails', async () => {
    record('get', RUN_URL, WAITING);
    const replies = record(
      'post',
      `${RUN_URL}/answers`,
      HttpResponse.json(errorBody('RUN_CHANGED', 'The run changed. Try again.', true), {
        status: 409,
      }),
      { ...WAITING, revision: 4, questions: [LENGTH_QUESTION] },
    );

    renderApp(`${CHAT}?run=${RUN_ID}`);
    await userEvent.click(
      within(
        await screen.findByRole('article', { name: 'How late may a user cancel a booking?' }),
      ).getByRole('button', { name: 'Answer' }),
    );
    fireEvent.change(composer(), { target: { value: CANCEL_ANSWER } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your reply was not saved. The run changed. Try again.',
    );
    expect(composer()).toHaveValue(CANCEL_ANSWER);

    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(replies).toHaveLength(2);
    });
    expect(replies[1]?.key).toBe(replies[0]?.key);
  });

  it('shows a refused answer as an error rather than hiding it', async () => {
    record('get', RUN_URL, WAITING);
    record(
      'post',
      `${RUN_URL}/answers`,
      HttpResponse.json(
        errorBody('PERMISSION_DENIED', 'This action requires the editor role on the project'),
        { status: 403 },
      ),
    );
    renderApp(`${CHAT}?run=${RUN_ID}`);
    await userEvent.click(
      within(
        await screen.findByRole('article', { name: 'How late may a user cancel a booking?' }),
      ).getByRole('button', { name: 'Answer' }),
    );
    fireEvent.change(composer(), { target: { value: CANCEL_ANSWER } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Your reply was not saved. This action requires the editor role on the project',
    );
  });

  it('restores a persisted run from the URL without starting or advancing anything', async () => {
    const created = record('post', `${API}/projects/${PROJECT_ID}/runs`, makeRun());
    const advanced = record('post', `${RUN_URL}/advance`, WAITING);
    record('get', RUN_URL, {
      ...WAITING,
      usage: { ...WAITING.usage, model_turns: 2, tool_calls: 3, clarification_rounds: 1 },
    });

    renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(screen.getByText('Loading the run…')).toBeInTheDocument();
    expect(
      await screen.findByText(/^I need 2 answers before I draft the backlog\./),
    ).toBeInTheDocument();
    expect(created).toHaveLength(0);
    expect(advanced).toHaveLength(0);

    const details = screen.getByRole('button', { name: 'Run details' });
    await userEvent.click(details);
    const popover = within(screen.getByRole('dialog', { name: 'Run details' }));
    expect(popover.getByText(RUN_ID)).toBeInTheDocument();
    expect(popover.getByText('Waiting for you')).toBeInTheDocument();
    expect(popover.getByText('2 / 6')).toBeInTheDocument();
    expect(popover.getByText('3 / 8')).toBeInTheDocument();
    expect(popover.getByText('1 / 2')).toBeInTheDocument();
    expect(popover.getByText('gemini · test-model')).toBeInTheDocument();
    expect(details).toHaveAttribute('aria-expanded', 'true');

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog', { name: 'Run details' })).not.toBeInTheDocument();
    expect(details).toHaveFocus();
  });

  it('shows a running run as working, with Stop in place of Send', async () => {
    record('get', RUN_URL, makeRun({ status: 'running', stage: 'draft', revision: 6 }));
    const advanced = record('post', `${RUN_URL}/advance`, async () => {
      await delay('infinite');
      return HttpResponse.json(READY);
    });
    const cancelled = record('post', `${RUN_URL}/cancel`, makeRun({ status: 'cancelled' }));

    renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(
      await screen.findByText('Drafting the backlog from your sources and answers…'),
    ).toBeInTheDocument();
    expect(screen.getByText(/the run is saved and resumes/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(advanced).toHaveLength(1);
    });

    await userEvent.click(screen.getByRole('button', { name: 'Stop the agent' }));

    expect(await within(screen.getByRole('main')).findByText('Run stopped')).toBeInTheDocument();
    expect(cancelled).toEqual([{ key: `cancel-${RUN_ID}`, body: null }]);
  });

  it('pauses on a failed step and retries it only when asked', async () => {
    const overloaded = makeRun({
      status: 'running',
      revision: 4,
      error: { code: 'MODEL_OVERLOADED', message: 'The model is overloaded.', retryable: true },
    });
    record('get', RUN_URL, overloaded);
    const advanced = record('post', `${RUN_URL}/advance`, READY);

    renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The last step failed and nothing was lost. The model is overloaded.',
    );
    expect(screen.queryByText('Reading the sources…')).not.toBeInTheDocument();
    expect(advanced).toHaveLength(0);

    await userEvent.click(screen.getByRole('button', { name: 'Try the step again' }));

    expect(await screen.findByText('Draft ready')).toBeInTheDocument();
    expect(advanced).toEqual([{ key: `advance-${RUN_ID}-4`, body: null }]);
  });

  it('offers a retry with the same key when the request to advance is lost', async () => {
    record('get', RUN_URL, makeRun());
    const advanced = record('post', `${RUN_URL}/advance`, HttpResponse.error(), WAITING);

    renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The run could not be advanced. The server could not be reached.',
    );
    expect(advanced).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: 'Try the step again' }));

    expect(
      await screen.findByRole('article', { name: 'How late may a user cancel a booking?' }),
    ).toBeInTheDocument();
    expect(advanced.map((request) => request.key)).toEqual([
      `advance-${RUN_ID}-1`,
      `advance-${RUN_ID}-1`,
    ]);
  });

  it('shows a failed run with its reason and a way to start again', async () => {
    record(
      'get',
      RUN_URL,
      makeRun({
        status: 'failed',
        problems: ['story S4 has no epic to belong to'],
        error: {
          code: 'INVALID_MODEL_OUTPUT',
          message: 'The model did not return a valid draft after its repair attempt',
          retryable: false,
        },
      }),
    );
    const advanced = record('post', `${RUN_URL}/advance`, READY);
    const router = renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(await within(screen.getByRole('main')).findByText('Run failed')).toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The model did not return a valid draft');
    expect(alert).toHaveTextContent('story S4 has no epic to belong to');
    expect(screen.queryByRole('button', { name: 'Stop the agent' })).not.toBeInTheDocument();
    expect(advanced).toHaveLength(0);

    await userEvent.click(screen.getByRole('button', { name: 'Start a new run' }));

    expect(
      await screen.findByRole('heading', { name: 'New chat for Study Room Booking' }),
    ).toBeInTheDocument();
    expect(router.state.location.search).toBe('');
  });

  it('shows the problems the agent could not fix on a draft that is ready', async () => {
    record('get', RUN_URL, { ...READY, problems: ['S1 criterion cites unknown block B99'] });

    renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(await screen.findByText('Draft ready')).toBeInTheDocument();
    expect(screen.getByText('S1 criterion cites unknown block B99')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('lists what the agent found and opens each citation on its source block or answer', async () => {
    record('get', RUN_URL, {
      ...READY,
      questions: [
        {
          ...CANCEL_QUESTION,
          status: 'answered',
          answer: CANCEL_ANSWER,
          answered_by: REVIEWER_ID,
          answered_at: '2026-10-13T10:00:00Z',
        },
      ],
      draft: {
        items: [],
        questions: [],
        statements: [
          {
            id: 'T1',
            kind: 'confirmed',
            summary: 'Users search rooms by date, time and capacity.',
            citations: [{ block_id: 'B2', quote: 'search rooms by date, time and capacity' }],
          },
          {
            id: 'T2',
            kind: 'exclusion',
            summary: 'Recurring reservations',
            citations: [{ block_id: 'B4', quote: 'Recurring reservations are out of scope' }],
          },
          {
            id: 'T3',
            kind: 'confirmed',
            summary: 'Cancellation up to one hour before',
            citations: [{ block_id: 'A1', quote: CANCEL_ANSWER }],
          },
        ],
      },
      block_refs: [
        { label: 'B2', source_block_id: BRIEF_BLOCKS[1]?.id ?? null, question_id: null },
        { label: 'B4', source_block_id: TRANSCRIPT_BLOCKS[1]?.id ?? null, question_id: null },
        { label: 'A1', source_block_id: null, question_id: CANCEL_QUESTION.id },
      ],
    });
    renderApp(`${CHAT}?run=${RUN_ID}`);

    const found = within(await screen.findByRole('list', { name: 'What the agent found' }));
    // Citations are named like everywhere else in the app, never by the draft's B2 or A1.
    await waitFor(() => {
      expect(found.getAllByRole('listitem').map((row) => row.textContent)).toEqual([
        'DecisionUsers search rooms by date, time and capacity.Brief ¶2',
        'ExcludedRecurring reservationsTranscript ¶2',
        'DecisionCancellation up to one hour beforeAnswer',
      ]);
    });

    const recurring = found.getByRole('button', {
      name: 'Transcript ¶2, evidence for: Recurring reservations',
    });
    await userEvent.click(recurring);
    let sheet = within(await screen.findByRole('dialog', { name: 'Evidence' }));
    expect(
      await sheet.findByText('transcript.md · Meeting transcript v1 · paragraph 2'),
    ).toBeVisible();
    expect(sheet.getByText('Recurring reservations are out of scope').tagName).toBe('MARK');
    await expectNoAccessibilityViolations();
    await userEvent.keyboard('{Escape}');
    expect(recurring).toHaveFocus();

    await userEvent.click(
      found.getByRole('button', {
        name: 'Answer, evidence for: Cancellation up to one hour before',
      }),
    );
    sheet = within(await screen.findByRole('dialog', { name: 'Evidence' }));
    expect(sheet.getByText(CANCEL_ANSWER)).toBeInTheDocument();
    expect(await sheet.findByText(/^Answer by Local Reviewer/)).toBeInTheDocument();
    expect(sheet.getByText('Question: How late may a user cancel a booking?')).toBeVisible();
  });

  it('says which backup provider a run fell back to', async () => {
    record('get', RUN_URL, {
      ...WAITING,
      provider: 'groq',
      fallback_reason: 'The primary provider was overloaded.',
    });

    renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(
      await screen.findByText(
        'The agent is using its backup provider (groq). The primary provider was overloaded.',
      ),
    ).toBeInTheDocument();
  });

  it('stops a run that waits for answers, once', async () => {
    record('get', RUN_URL, WAITING);
    const cancelled = record('post', `${RUN_URL}/cancel`, { ...WAITING, status: 'cancelled' });

    renderApp(`${CHAT}?run=${RUN_ID}`);
    fireEvent.click(await screen.findByRole('button', { name: 'Stop the run' }));
    fireEvent.click(screen.getByRole('button', { name: 'Stop the run' }));

    expect(await within(screen.getByRole('main')).findByText('Run stopped')).toBeInTheDocument();
    expect(cancelled).toEqual([{ key: `cancel-${RUN_ID}`, body: null }]);
    expect(screen.getByRole('button', { name: 'Start a new run' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Answer' })).not.toBeInTheDocument();
  });

  it('says when a run cannot be loaded and lets the reviewer start another', async () => {
    record(
      'get',
      RUN_URL,
      HttpResponse.json(errorBody('NOT_FOUND', 'Run not found'), { status: 404 }),
    );

    renderApp(`${CHAT}?run=${RUN_ID}`);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the run. Run not found',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Start a new run' }));
    expect(await screen.findByRole('button', { name: 'Start run' })).toBeInTheDocument();
  });

  it('asks for sources first when the project has none, and offers the last run', async () => {
    window.localStorage.setItem(LAST_RUN_KEY, RUN_ID);
    server.use(http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: [] })));
    record('get', RUN_URL, READY);

    renderApp(CHAT);

    expect(await screen.findByText('TXT or Markdown, up to 512 KB each')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start run' })).toBeDisabled();
    expect(
      within(screen.getByRole('main')).getAllByRole('button', { name: 'Add sources' }),
    ).not.toHaveLength(0);
    expect(composer()).toBeDisabled();
    expect(composer()).toHaveAttribute(
      'placeholder',
      'Add sources and start the run to chat with ScopeSteps',
    );

    await userEvent.click(
      screen.getByRole('button', { name: 'Open the last run started in this browser' }),
    );

    expect(await screen.findByText('Draft ready')).toBeInTheDocument();
  });

  it('gives a viewer the thread without answer, skip, start, stop or upload controls', async () => {
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));
    const advanced = record('post', `${RUN_URL}/advance`, WAITING);
    record('get', RUN_URL, WAITING);

    renderApp(`${CHAT}?run=${RUN_ID}`);

    await screen.findByRole('article', { name: 'How late may a user cancel a booking?' });
    await waitFor(() => {
      expect(composer()).toHaveAttribute(
        'placeholder',
        'View-only access. An editor can reply to the agent.',
      );
    });
    expect(composer()).toBeDisabled();
    for (const name of ['Answer', 'Skip', 'Stop the run', 'Stop the agent', 'Add sources']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(advanced).toHaveLength(0);
  });

  it('gives a viewer the new chat without start or upload controls', async () => {
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));

    renderApp(CHAT);

    expect(await screen.findByText('2 sources added · 60 of 6,000 words')).toBeInTheDocument();
    await screen.findByRole('button', { name: /Local Reviewer/ });
    expect(screen.queryByRole('button', { name: 'Start run' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add sources' })).not.toBeInTheDocument();
  });

  it('has no accessibility violations as a new chat', async () => {
    renderApp(CHAT);
    await screen.findByText('2 sources added · 60 of 6,000 words');
    await expectNoAccessibilityViolations();
  });

  it('has no accessibility violations with questions and the composer in use', async () => {
    record('get', RUN_URL, WAITING);
    renderApp(`${CHAT}?run=${RUN_ID}`);
    await userEvent.click(
      within(
        await screen.findByRole('article', { name: 'How late may a user cancel a booking?' }),
      ).getByRole('button', { name: 'Answer' }),
    );
    await screen.findAllByRole('button', { name: 'Brief ¶2' });
    await expectNoAccessibilityViolations();
  });
});
