import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  APPROVER_ID,
  BASELINE_ID,
  CANDIDATE,
  CANDIDATE_ID,
  CANDIDATE_URL,
  CHANGE_RUN_ID,
  candidateHandlers,
  changeRequest,
  decidedCandidate,
} from '@/test/changeFixtures';
import { API, VERSIONS_URL } from '@/test/handlers';
import { APPROVER, errorBody, PROJECT, PROJECT_ID, VIEWER, versionSummary } from '@/test/fixtures';
import { projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { Decision } from './types';

const PAGE = `/projects/${PROJECT_ID}/backlog?version=${CANDIDATE_ID}`;
const DECISION_ID = '019a3a5e-0000-7000-8000-00000000030a';
const ANSWER_URL = `${API}/backlogs/${CANDIDATE_ID}/candidate-decisions/${DECISION_ID}`;
const SUBJECT = 'Clashing weeks';

/** A clarification skipped during the change run, now a decision on the candidate. */
const SKIPPED: Decision = {
  id: DECISION_ID,
  kind: 'missing_decision',
  status: 'skipped',
  subject: SUBJECT,
  question: 'What happens when a week in the series clashes with an existing booking?',
  why_it_matters: 'It decides whether a series can be booked at all.',
  evidence: [],
  affected_item_ids: [],
  question_id: '019a3a5e-0000-7000-8000-0000000000da',
  answer: null,
  decided_by: APPROVER_ID,
  decided_at: '2026-10-15T10:00:00Z',
};
const REVERSED = decidedCandidate('reverse');
const WITH_SKIPPED = {
  ...REVERSED,
  decisions: [...REVERSED.decisions, SKIPPED],
};
const ANSWERED = {
  ...WITH_SKIPPED,
  revision: 3,
  decisions: [
    ...REVERSED.decisions,
    { ...SKIPPED, status: 'answered' as const, answer: 'Skip the clashing week.' },
  ],
};

function main() {
  return within(screen.getByRole('main'));
}

function decisionRow() {
  return within(main().getByRole('listitem', { name: SUBJECT }));
}

function recordAnswers(reply: () => Response) {
  const sent: { key: string | null; body: unknown }[] = [];
  server.use(
    http.post(ANSWER_URL, async ({ request }) => {
      sent.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      return reply();
    }),
  );
  return sent;
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Answering a change candidate’s open decision on the backlog', () => {
  it('lets an approver answer it at the revision on screen, then offers approval', async () => {
    server.use(...candidateHandlers(APPROVER));
    server.use(http.get(CANDIDATE_URL, () => HttpResponse.json(WITH_SKIPPED)));
    const sent = recordAnswers(() => HttpResponse.json(ANSWERED));
    renderApp(PAGE);

    await main().findByRole('listitem', { name: SUBJECT });
    await userEvent.click(decisionRow().getByRole('button', { name: `Answer: ${SUBJECT}` }));
    await expectNoAccessibilityViolations();
    await userEvent.type(
      decisionRow().getByRole('textbox', { name: 'Your answer' }),
      'Skip the clashing week.',
    );
    await userEvent.click(decisionRow().getByRole('button', { name: 'Save answer' }));

    expect(await decisionRow().findByText('Skip the clashing week.')).toBeVisible();
    expect(sent).toHaveLength(1);
    expect(sent[0]?.body).toEqual({ expected_revision: 2, answer: 'Skip the clashing week.' });
    expect(sent[0]?.key).toMatch(/.+/);
    expect(main().getByRole('button', { name: 'Approve as v2…' })).toBeEnabled();
  });

  it('tells anyone but an approver who must answer, without the form', async () => {
    server.use(...candidateHandlers(VIEWER));
    server.use(http.get(CANDIDATE_URL, () => HttpResponse.json(WITH_SKIPPED)));
    renderApp(PAGE);

    await main().findByRole('listitem', { name: SUBJECT });
    expect(
      decisionRow().getByText(
        'Waiting for a Product owner to answer it before the candidate can be approved.',
      ),
    ).toBeVisible();
    expect(decisionRow().queryByRole('button', { name: /Answer/ })).toBeNull();
    await expectNoAccessibilityViolations();
  });

  it.each([
    ['VERSION_CHANGED', 'Someone else changed this candidate after you opened it.'],
    ['DECISION_ALREADY_ANSWERED', 'Someone else changed this candidate after you opened it.'],
    [
      'VERSION_NOT_IN_REVIEW',
      'This version was approved or rejected meanwhile, so it can no longer change.',
    ],
  ])('offers a reload on a %s conflict', async (code, text) => {
    server.use(...candidateHandlers(APPROVER));
    let current = WITH_SKIPPED;
    server.use(http.get(CANDIDATE_URL, () => HttpResponse.json(current)));
    recordAnswers(() => {
      current = ANSWERED;
      return HttpResponse.json(errorBody(code, 'Conflict.'), { status: 409 });
    });
    renderApp(PAGE);

    await main().findByRole('listitem', { name: SUBJECT });
    await userEvent.click(decisionRow().getByRole('button', { name: `Answer: ${SUBJECT}` }));
    await userEvent.type(decisionRow().getByRole('textbox', { name: 'Your answer' }), 'An answer');
    await userEvent.click(decisionRow().getByRole('button', { name: 'Save answer' }));

    const alert = await main().findByRole('alert');
    expect(alert).toHaveTextContent(text);
    await userEvent.click(within(alert).getByRole('button', { name: 'Reload' }));
    expect(await decisionRow().findByText('Skip the clashing week.')).toBeVisible();
    expect(main().queryByRole('alert')).toBeNull();
  });
});

describe('A rejected change candidate', () => {
  it('is named as CR-3’s candidate, not a draft, and links to the change requests', async () => {
    server.use(...candidateHandlers(VIEWER));
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
      http.get(CANDIDATE_URL, () => HttpResponse.json({ ...CANDIDATE, state: 'rejected' })),
      http.get(`${API}/change-requests/${changeRequest().id}`, () =>
        HttpResponse.json(changeRequest({ status: 'rejected' })),
      ),
      http.get(VERSIONS_URL, () =>
        HttpResponse.json({
          versions: [
            versionSummary(CANDIDATE_ID, {
              state: 'rejected',
              base_version_id: BASELINE_ID,
              run_id: CHANGE_RUN_ID,
            }),
            versionSummary(BASELINE_ID, { number: 1 }),
          ],
          next_cursor: null,
        }),
      ),
    );
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Candidate v2 · rejected' })).toBeVisible();
    expect(main().getByText(/v1 is still the current baseline, unchanged\./)).toBeVisible();
    expect(await main().findByRole('link', { name: 'See CR-3' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/changes`,
    );
    const select = await main().findByRole('combobox', { name: 'Version' });
    expect(within(select).getByRole('option', { name: /^Rejected candidate/ })).toBeDefined();
    expect(main().queryByText(/Draft r\d · rejected/)).toBeNull();
    await expectNoAccessibilityViolations();
  });
});
