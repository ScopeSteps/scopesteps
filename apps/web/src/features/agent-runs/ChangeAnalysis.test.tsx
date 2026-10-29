import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  CANDIDATE_ID,
  CHANGE_REQUEST_ID,
  CHANGE_RUN_ID,
  CHANGE_SET_URL,
  CANDIDATE_URL,
  candidateHandlers,
  changeRequest,
  decidedCandidate,
  IMPACT,
  SCOPE_DECISION_URL,
} from '@/test/changeFixtures';
import {
  APPROVER,
  CANCEL_QUESTION,
  errorBody,
  makeRun,
  PROJECT_ID,
  REVIEWER,
  REVIEWER_ID,
  VIEWER,
} from '@/test/fixtures';
import { API, MESSAGES_URL, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { Message } from './types';

const CHAT = `/projects/${PROJECT_ID}/chat`;
const AT = '2026-10-15T09:00:00Z';
const EXCLUSION = 'Recurring reservations are out of scope for release one.';
const CHANGE_QUESTION = {
  ...CANCEL_QUESTION,
  id: '019a3a5e-0000-7000-8000-0000000000da',
  subject: 'Clashing weeks',
  text: 'What happens when a week in the series clashes with an existing booking?',
};

let count = 0;
function message(overrides: Partial<Message>): Message {
  count += 1;
  return {
    id: `019a3a5e-0000-7000-8000-${String(count).padStart(12, '0')}`,
    author: null,
    claims: [],
    created_at: AT,
    event: null,
    change_request_id: null,
    baseline_version: null,
    kind: 'message',
    question: null,
    question_id: null,
    role: 'agent',
    run_id: CHANGE_RUN_ID,
    text: '',
    ...overrides,
  };
}

const REQUEST = message({
  kind: 'change_request',
  role: 'user',
  text: 'Clubs want to book the same room every week.',
  author: { user_id: REVIEWER_ID, display_name: REVIEWER.display_name },
});
const ANALYSIS = message({
  kind: 'analysis',
  text: 'Weekly bookings bring back recurring reservations, which v1 excludes.',
  claims: [
    {
      basis: 'agent',
      text: 'Weekly bookings bring back recurring reservations, which v1 excludes.',
      citations: [],
    },
  ],
});
const QUESTION = message({
  kind: 'question',
  question_id: CHANGE_QUESTION.id,
  text: CHANGE_QUESTION.text,
  question: {
    id: CHANGE_QUESTION.id,
    run_id: CHANGE_RUN_ID,
    round: 1,
    status: 'open',
    subject: CHANGE_QUESTION.subject,
    why_it_matters: CHANGE_QUESTION.why_it_matters,
    answer: null,
    answered_at: null,
    answered_by: null,
  },
});
const READY = message({
  kind: 'event',
  role: 'system',
  event: 'change.ready_for_review',
  text: 'Change ready for review',
});
const NO_CHANGE = message({
  kind: 'event',
  role: 'system',
  event: 'change.no_change_needed',
  text: 'No change needed',
});

const CHANGE_RUN = {
  id: CHANGE_RUN_ID,
  mode: 'change' as const,
  stage: 'change' as const,
  change_request_id: CHANGE_REQUEST_ID,
};

/** The thread, oldest first, and the change run as it stands. */
function serveThread(thread: Message[], run = makeRun({ ...CHANGE_RUN, status: 'running' })) {
  server.use(
    http.get(MESSAGES_URL, () =>
      HttpResponse.json({ messages: [...thread].reverse(), next_cursor: null, active_run: null }),
    ),
    http.get(`${API}/runs/${CHANGE_RUN_ID}`, () => HttpResponse.json(run)),
  );
}

const READY_RUN = makeRun({
  ...CHANGE_RUN,
  status: 'ready_for_review',
  candidate_version_id: CANDIDATE_ID,
});

function thread() {
  return within(screen.getByRole('main'));
}

async function scopeCard() {
  return within(
    await thread().findByRole('article', { name: 'Decision needed: reverse the exclusion?' }),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  server.use(...projectHandlers());
  server.use(...candidateHandlers());
});

describe('A change request’s analysis in the chat', () => {
  it('shows the request, the agent’s analysis and the change run’s questions', async () => {
    serveThread(
      [REQUEST, ANALYSIS, QUESTION],
      makeRun({ ...CHANGE_RUN, status: 'waiting_for_input', questions: [CHANGE_QUESTION] }),
    );
    renderApp(CHAT);

    expect(await thread().findByText('Change analysis')).toBeVisible();
    expect(thread().getByText(ANALYSIS.text)).toBeVisible();
    expect(thread().getByText('Clubs want to book the same room every week.')).toBeVisible();
    const question = within(await thread().findByRole('article', { name: CHANGE_QUESTION.text }));
    expect(await question.findByRole('button', { name: /Answer/ })).toBeVisible();
    await expectNoAccessibilityViolations();
  });

  it('shows what the candidate changes and its scope decision, waiting for a Product owner', async () => {
    serveThread([REQUEST, ANALYSIS, READY], READY_RUN);
    renderApp(CHAT);

    const card = await scopeCard();
    expect(card.getByText(`“${EXCLUSION}”`, { exact: false })).toBeVisible();
    expect(
      card.getByText(
        'Waiting for a Product owner. Your role (Business analyst) can’t make scope decisions.',
      ),
    ).toBeVisible();
    expect(card.queryByRole('button', { name: /reverse it|keep it/ })).toBeNull();
    expect(thread().getByRole('list', { name: 'Proposed changes' })).toHaveTextContent(
      '+Added 1~Changed 1−Removed 1',
    );
    expect(thread().getByRole('link', { name: /View in Backlog/ })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog?version=${CANDIDATE_ID}`,
    );
    await expectNoAccessibilityViolations();
  });

  it('sums up the change and links to it on the Backlog and Change Requests pages', async () => {
    const ready = { ...READY, change_request_id: CHANGE_REQUEST_ID, impact: IMPACT };
    serveThread([REQUEST, ANALYSIS, ready], READY_RUN);
    renderApp(CHAT);

    expect(
      await thread().findByText('Adds 1 story, changes 1, removes 1. Raises 1 scope decision.'),
    ).toBeVisible();
    expect(await thread().findByRole('link', { name: 'View in Backlog: CR-3' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/backlog?version=${CANDIDATE_ID}`,
    );
    expect(thread().getByRole('link', { name: 'View in Change Requests: CR-3' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/changes?request=${CHANGE_REQUEST_ID}`,
    );
    await expectNoAccessibilityViolations();
  });

  it('tells a viewer who must decide', async () => {
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));
    serveThread([REQUEST, ANALYSIS, READY], READY_RUN);
    renderApp(CHAT);

    expect(
      (await scopeCard()).getByText(
        'Waiting for a Product owner. Your role (Viewer) can’t make scope decisions.',
      ),
    ).toBeVisible();
  });

  it.each([
    ['Yes, reverse it', 'reverse', 'Reversed'],
    ['No, keep it', 'keep', 'Kept'],
  ] as const)('lets an approver choose “%s”', async (button, outcome, shown) => {
    server.use(http.get(`${API}/me`, () => HttpResponse.json(APPROVER)));
    const sent: unknown[] = [];
    server.use(
      http.post(SCOPE_DECISION_URL, async ({ request }) => {
        sent.push(await request.json());
        return HttpResponse.json(decidedCandidate(outcome));
      }),
    );
    serveThread([REQUEST, ANALYSIS, READY], READY_RUN);
    renderApp(CHAT);

    await userEvent.click((await scopeCard()).getByRole('button', { name: button }));

    const decided = within(await thread().findByRole('article', { name: 'Scope decision' }));
    expect(decided.getByText(shown)).toBeVisible();
    expect(sent).toEqual([{ expected_revision: 1, outcome }]);
  });

  it('opens the quoted evidence of the earlier exclusion in the evidence sheet', async () => {
    serveThread([REQUEST, ANALYSIS, READY], READY_RUN);
    renderApp(CHAT);

    await userEvent.click(
      await (
        await scopeCard()
      ).findByRole('button', { name: `Transcript ¶2, evidence for: ${EXCLUSION}` }),
    );

    const sheet = within(await screen.findByRole('dialog', { name: 'Evidence' }));
    expect(await sheet.findByText('Recurring reservations')).toBeVisible();
    expect(await sheet.findByText(/Recurring reservations are out of scope/)).toBeVisible();
  });

  it('names a citation of the change request by its kind, though no source lists it', async () => {
    const requestVersionId = '019a3a5e-0000-7000-8000-0000000000b9';
    const blockId = '019a3a5e-0000-7000-8000-0000000000bb';
    const quote = 'Clubs want to book the same room every week.';
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}/sources/${requestVersionId}/blocks`, () =>
        HttpResponse.json([
          {
            id: blockId,
            source_version_id: requestVersionId,
            source_kind: 'change_request',
            ordinal: 1,
            text: quote,
            locator: { paragraph: 1, start_offset: 0, end_offset: quote.length },
          },
        ]),
      ),
    );
    const cited = message({
      kind: 'analysis',
      text: 'Adds weekly bookings.',
      claims: [
        {
          basis: 'cited',
          text: 'Adds weekly bookings.',
          citations: [
            {
              quote,
              question_id: null,
              evidence: {
                source_version_id: requestVersionId,
                block_id: blockId,
                quote,
                relationship: 'supporting',
              },
            },
          ],
        },
      ],
    });
    serveThread([REQUEST, cited], makeRun({ ...CHANGE_RUN, status: 'completed' }));
    renderApp(CHAT);

    expect(await thread().findByRole('button', { name: /^Request ¶1/ })).toBeVisible();
  });

  it('says so when no change is needed', async () => {
    serveThread([REQUEST, ANALYSIS, NO_CHANGE], makeRun({ ...CHANGE_RUN, status: 'completed' }));
    renderApp(CHAT);

    expect(await thread().findByRole('note')).toHaveTextContent('No change needed');
    expect(
      thread().getByText(
        'No change needed. No candidate was saved, and the approved baseline stays as it is.',
      ),
    ).toBeVisible();
    expect(thread().queryByRole('article', { name: /reverse/ })).toBeNull();
  });

  it('says so when what the candidate changes cannot be loaded', async () => {
    server.use(
      http.get(CHANGE_SET_URL, () =>
        HttpResponse.json(errorBody('NOT_FOUND', 'Not found.'), { status: 404 }),
      ),
    );
    serveThread([REQUEST, ANALYSIS, READY], READY_RUN);
    renderApp(CHAT);

    expect(await thread().findByRole('alert')).toHaveTextContent(
      'Could not load what this candidate changes.',
    );
  });

  it.each([
    ['approved', 'reverse', 'CR-3 was approved as baseline v2.', 2],
    ['rejected', 'keep', 'CR-3 was rejected; the baseline stays v1.', 1],
  ] as const)(
    'reports once, as its own event, that an approver %s the candidate',
    async (status, answer, text, baseline) => {
      server.use(
        http.get(CANDIDATE_URL, () =>
          HttpResponse.json({ ...decidedCandidate(answer), state: status }),
        ),
        http.get(`${API}/change-requests/${CHANGE_REQUEST_ID}`, () =>
          HttpResponse.json(
            changeRequest({ status, approved_version_number: status === 'approved' ? 2 : null }),
          ),
        ),
      );
      const outcome = message({
        kind: 'event',
        role: 'system',
        event: `change.${status}`,
        change_request_id: CHANGE_REQUEST_ID,
        baseline_version: baseline,
        text,
      });
      serveThread([REQUEST, ANALYSIS, READY, outcome], READY_RUN);
      renderApp(CHAT);

      expect(await thread().findByText(text)).toBeVisible();
      expect(thread().getAllByText(new RegExp(`CR-3 (was )?${status}`))).toHaveLength(1);
      expect(await thread().findByRole('list', { name: 'Proposed changes' })).toHaveTextContent(
        '+Added 1~Changed 1−Removed 1',
      );
      expect(await thread().findByRole('link', { name: 'Change requests: CR-3' })).toHaveAttribute(
        'href',
        `/projects/${PROJECT_ID}/changes?request=${CHANGE_REQUEST_ID}`,
      );
      if (status === 'approved') {
        expect(thread().getByRole('link', { name: /Open baseline v2/ })).toHaveAttribute(
          'href',
          `/projects/${PROJECT_ID}/backlog?version=${CANDIDATE_ID}`,
        );
      } else {
        expect(thread().queryByRole('link', { name: /Open baseline/ })).not.toBeInTheDocument();
      }
      await expectNoAccessibilityViolations();
    },
  );
});
