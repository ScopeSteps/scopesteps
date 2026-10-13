import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { delay, http, HttpResponse } from 'msw';
import { useState } from 'react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { AgentRunView } from '@/features/agent-runs';
import {
  BRIEF,
  BRIEF_BLOCKS,
  CANCEL_ANSWER,
  CANCEL_QUESTION,
  errorBody,
  LENGTH_QUESTION,
  makeRun,
  PROJECT_ID,
  REVIEWER,
  REVIEWER_ID,
  RUN_ID,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
  VERSION_ID,
} from '@/test/fixtures';
import { server } from '@/test/server';

import type { Run } from './types';

const RUN_URL = `*/api/v1/runs/${RUN_ID}`;
const SOURCES_URL = `*/api/v1/projects/${PROJECT_ID}/sources`;
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

function RunScreen({ initialRunId }: { initialRunId: string | null }) {
  const [runId, setRunId] = useState(initialRunId);
  return <AgentRunView projectId={PROJECT_ID} runId={runId} onRunSelected={setRunId} />;
}

function renderRun(initialRunId: string | null = RUN_ID) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RunScreen initialRunId={initialRunId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)),
    http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] })),
    http.get(`${SOURCES_URL}/${BRIEF.id}/blocks`, () => HttpResponse.json(BRIEF_BLOCKS)),
    http.get(`${SOURCES_URL}/${TRANSCRIPT.id}/blocks`, () => HttpResponse.json(TRANSCRIPT_BLOCKS)),
  );
});

describe('AgentRunView', () => {
  it('starts one run on the stored sources and shows what the agent asks, with its context', async () => {
    const created = record('post', `*/api/v1/projects/${PROJECT_ID}/runs`, makeRun());
    const advanced = record('post', `${RUN_URL}/advance`, WAITING);
    record('get', RUN_URL, makeRun());

    renderRun(null);
    expect(await screen.findByText('Project brief: brief.md, version 1')).toBeInTheDocument();
    const start = screen.getByRole('button', { name: 'Generate backlog' });
    fireEvent.click(start);
    fireEvent.click(start);

    expect(await screen.findByText('Waiting for your answers')).toBeInTheDocument();
    expect(created).toHaveLength(1);
    expect(created[0]?.body).toEqual({
      mode: 'initial',
      source_version_ids: [BRIEF.id, TRANSCRIPT.id],
    });
    expect(created[0]?.key).toBeTruthy();
    expect(advanced).toEqual([{ key: `advance-${RUN_ID}-1`, body: null }]);

    const question = within(screen.getByRole('article', { name: 'Cancellation and no-shows' }));
    expect(question.getByText('How late may a user cancel a booking?')).toBeInTheDocument();
    expect(question.getByText('The sources leave the cancellation rule open.')).toBeInTheDocument();
    expect(await question.findByText(/A booking can last up to 4 hours\./)).toBeInTheDocument();
    expect(question.getByText('Project brief: brief.md, version 1')).toBeInTheDocument();
    expect(question.getByText(/Paragraph 2/)).toBeInTheDocument();
  });

  it('saves an answer and a skip once each, then resumes to the finished draft', async () => {
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

    renderRun();
    const cancellation = within(
      await screen.findByRole('article', { name: 'Cancellation and no-shows' }),
    );
    const submit = cancellation.getByRole('button', { name: 'Submit answer' });
    expect(submit).toBeDisabled();
    fireEvent.change(cancellation.getByLabelText('Your answer'), {
      target: { value: `  ${CANCEL_ANSWER}  ` },
    });
    fireEvent.click(submit);
    fireEvent.click(submit);

    expect(
      await cancellation.findByText(`Answer by Local Reviewer:`, { exact: false }),
    ).toBeInTheDocument();
    expect(cancellation.getByText(CANCEL_ANSWER)).toBeInTheDocument();
    expect(cancellation.queryByLabelText('Your answer')).not.toBeInTheDocument();
    expect(advanced).toHaveLength(0);

    const length = within(screen.getByRole('article', { name: 'Maximum booking length' }));
    fireEvent.click(length.getByRole('button', { name: 'Skip question' }));

    expect(await screen.findByText('Ready for review')).toBeInTheDocument();
    expect(length.getByText('Skipped: still an open decision')).toBeInTheDocument();
    expect(length.getByText(/No answer was assumed/)).toBeInTheDocument();
    expect(replies.map((reply) => reply.body)).toEqual([
      { question_id: CANCEL_QUESTION.id, answer: CANCEL_ANSWER, skip: false },
      { question_id: LENGTH_QUESTION.id, skip: true },
    ]);
    expect(new Set(replies.map((reply) => reply.key)).size).toBe(2);
    expect(advanced).toEqual([{ key: `advance-${RUN_ID}-5`, body: null }]);
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

    renderRun();
    const cancellation = within(
      await screen.findByRole('article', { name: 'Cancellation and no-shows' }),
    );
    fireEvent.change(cancellation.getByLabelText('Your answer'), {
      target: { value: CANCEL_ANSWER },
    });
    fireEvent.click(cancellation.getByRole('button', { name: 'Submit answer' }));

    expect(await cancellation.findByRole('alert')).toHaveTextContent(
      'Your reply was not saved. The run changed. Try again.',
    );
    expect(cancellation.getByLabelText('Your answer')).toHaveValue(CANCEL_ANSWER);

    fireEvent.click(cancellation.getByRole('button', { name: 'Submit answer' }));

    await waitFor(() => {
      expect(replies).toHaveLength(2);
    });
    expect(replies[1]?.key).toBe(replies[0]?.key);
  });

  it('resumes a persisted run after a refresh without starting or advancing anything', async () => {
    const created = record('post', `*/api/v1/projects/${PROJECT_ID}/runs`, makeRun());
    const advanced = record('post', `${RUN_URL}/advance`, WAITING);
    record('get', RUN_URL, WAITING);

    renderRun();

    expect(screen.getByText('Loading the run…')).toBeInTheDocument();
    expect(await screen.findByText('Waiting for your answers')).toBeInTheDocument();
    expect(
      screen.getByText('The agent needs 2 answers before it can draft the backlog.'),
    ).toBeInTheDocument();
    expect(screen.getByText(/Model calls 0 of 6/)).toBeInTheDocument();
    expect(created).toHaveLength(0);
    expect(advanced).toHaveLength(0);
  });

  it('shows a running run as running while a step is in flight', async () => {
    record('get', RUN_URL, makeRun({ status: 'running', stage: 'draft', revision: 6 }));
    const advanced = record('post', `${RUN_URL}/advance`, async () => {
      await delay('infinite');
      return HttpResponse.json(READY);
    });

    renderRun();

    expect(await screen.findByText('Running: writing the draft')).toBeInTheDocument();
    expect(screen.getByText(/the run is saved and resumes/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel run' })).toBeEnabled();
    await waitFor(() => {
      expect(advanced).toHaveLength(1);
    });
  });

  it('pauses on a failed step and retries it only when asked', async () => {
    const overloaded = makeRun({
      status: 'running',
      revision: 4,
      error: { code: 'MODEL_OVERLOADED', message: 'The model is overloaded.', retryable: true },
    });
    record('get', RUN_URL, overloaded);
    const advanced = record('post', `${RUN_URL}/advance`, READY);

    renderRun();

    expect(await screen.findByText('Paused: the last step did not finish')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The last step failed and nothing was lost. The model is overloaded.',
    );
    expect(advanced).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Try the step again' }));

    expect(await screen.findByText('Ready for review')).toBeInTheDocument();
    expect(advanced).toEqual([{ key: `advance-${RUN_ID}-4`, body: null }]);
  });

  it('offers a retry with the same key when the request to advance is lost', async () => {
    record('get', RUN_URL, makeRun());
    const advanced = record('post', `${RUN_URL}/advance`, HttpResponse.error(), WAITING);

    renderRun();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The run could not be advanced. The server could not be reached.',
    );
    expect(screen.getByText('Paused: the last step did not finish')).toBeInTheDocument();
    expect(advanced).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', { name: 'Try the step again' }));

    expect(await screen.findByText('Waiting for your answers')).toBeInTheDocument();
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

    renderRun();

    expect(await screen.findByText('Failed')).toBeInTheDocument();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The model did not return a valid draft');
    expect(alert).toHaveTextContent('story S4 has no epic to belong to');
    expect(screen.queryByRole('button', { name: 'Cancel run' })).not.toBeInTheDocument();
    expect(advanced).toHaveLength(0);

    fireEvent.click(within(alert).getByRole('button', { name: 'Start a new run' }));

    expect(await screen.findByRole('heading', { name: 'Generate a backlog' })).toBeInTheDocument();
  });

  it('shows the problems the agent could not fix on a draft that is ready', async () => {
    record('get', RUN_URL, { ...READY, problems: ['S1 criterion cites unknown block B99'] });

    renderRun();

    expect(await screen.findByText('Ready for review')).toBeInTheDocument();
    expect(screen.getByText('S1 criterion cites unknown block B99')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('cancels an active run once', async () => {
    record('get', RUN_URL, WAITING);
    const cancelled = record('post', `${RUN_URL}/cancel`, { ...WAITING, status: 'cancelled' });

    renderRun();
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel run' }));

    expect(await screen.findByText('Cancelled')).toBeInTheDocument();
    expect(cancelled).toEqual([{ key: `cancel-${RUN_ID}`, body: null }]);
    expect(screen.getByRole('button', { name: 'Start a new run' })).toBeInTheDocument();
  });

  it('says when a run cannot be loaded and lets the reviewer start another', async () => {
    record(
      'get',
      RUN_URL,
      HttpResponse.json(errorBody('NOT_FOUND', 'Run not found'), { status: 404 }),
    );

    renderRun();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the run. Run not found',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Start a new run' }));
    expect(await screen.findByRole('button', { name: 'Generate backlog' })).toBeInTheDocument();
  });

  it('asks for sources first when the project has none, and offers the last run', async () => {
    window.localStorage.setItem(`scopesteps:last-run:${PROJECT_ID}`, RUN_ID);
    server.use(http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: [] })));
    record('get', RUN_URL, READY);

    renderRun(null);

    expect(
      await screen.findByRole('link', { name: 'Upload a project brief and a meeting transcript' }),
    ).toHaveAttribute('href', `/projects/${PROJECT_ID}/sources`);
    expect(screen.queryByRole('button', { name: 'Generate backlog' })).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'Open the last run started in this browser' }),
    );

    expect(await screen.findByText('Ready for review')).toBeInTheDocument();
  });
});
