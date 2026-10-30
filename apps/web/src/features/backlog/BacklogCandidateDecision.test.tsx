import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import type { components } from '@scopesteps/api-client';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  ADDED_STORY,
  APPROVER_ID,
  BASELINE_ID,
  CANDIDATE,
  CANDIDATE_ID,
  CANDIDATE_URL,
  CHANGE_REQUEST_ID,
  CHANGE_RUN_ID,
  candidateHandlers,
  changeRequest,
  decidedCandidate,
  SCOPE_DECISION,
  SCOPE_DECISION_ID,
} from '@/test/changeFixtures';
import {
  APPROVER,
  errorBody,
  makeReview,
  PROJECT,
  PROJECT_ID,
  VIEWER,
  versionSummary,
} from '@/test/fixtures';
import { API, projectHandlers, VERSIONS_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Schemas = components['schemas'];

const PAGE = `/projects/${PROJECT_ID}/backlog?version=${CANDIDATE_ID}`;
const REVIEW_URL = `${API}/backlogs/${CANDIDATE_ID}/review`;
const APPROVE_URL = `${API}/backlogs/${CANDIDATE_ID}/approve`;
const REJECT_URL = `${API}/backlogs/${CANDIDATE_ID}/reject`;
const REVERSED = decidedCandidate('reverse');
const KEPT = decidedCandidate('keep');

function decision(kind: 'approved' | 'rejected') {
  return {
    id: '019a3a5e-0000-7000-8000-000000000402',
    version_id: CANDIDATE_ID,
    decision: kind,
    decided_by: APPROVER_ID,
    revision: REVERSED.revision,
    content_hash: REVERSED.content_hash,
    decided_at: '2026-10-15T12:00:00Z',
    baseline_version: kind === 'approved' ? 2 : 1,
    current_baseline_id: kind === 'approved' ? CANDIDATE_ID : BASELINE_ID,
    change_request_id: CHANGE_REQUEST_ID,
    change_request_status: kind,
  };
}

interface Sent {
  key: string | null;
  body: unknown;
}

/**
 * CR-3's candidate, as an approver sees it once `candidate` is the version on screen; approval
 * and rejection answer with `approve` and `reject`, and the server's view follows the outcome.
 */
function serveDecision({
  candidate = REVERSED,
  approve = () => HttpResponse.json(decision('approved')),
  reject = () => HttpResponse.json(decision('rejected')),
}: {
  candidate?: typeof CANDIDATE;
  approve?: () => Response;
  reject?: () => Response;
} = {}) {
  let outcome: 'approved' | 'rejected' | null = null;
  const reviews: Sent[] = [];
  const approvals: Sent[] = [];
  const rejections: Sent[] = [];
  server.use(...candidateHandlers(APPROVER));
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        roles: ['approver'],
        status:
          outcome === 'approved'
            ? {
                state: 'baseline',
                baseline_version: 2,
                baseline_version_id: CANDIDATE_ID,
                open_version_id: null,
              }
            : {
                state: outcome === 'rejected' ? 'baseline' : 'candidate_in_review',
                baseline_version: 1,
                baseline_version_id: BASELINE_ID,
                open_version_id: outcome === 'rejected' ? null : CANDIDATE_ID,
              },
      }),
    ),
    http.get(CANDIDATE_URL, () =>
      HttpResponse.json(outcome ? { ...candidate, state: outcome } : candidate),
    ),
    http.get(VERSIONS_URL, () =>
      HttpResponse.json({
        versions: [
          outcome === 'approved'
            ? versionSummary(CANDIDATE_ID, { number: 2, base_version_id: BASELINE_ID })
            : versionSummary(CANDIDATE_ID, {
                state: outcome ?? 'in_review',
                base_version_id: BASELINE_ID,
                run_id: CHANGE_RUN_ID,
              }),
          versionSummary(BASELINE_ID, { number: 1 }),
        ],
        next_cursor: null,
      }),
    ),
    http.get(`${API}/change-requests/${CHANGE_REQUEST_ID}`, () =>
      HttpResponse.json(changeRequest({ status: outcome ?? 'in_review' })),
    ),
    http.post(REVIEW_URL, async ({ request }) => {
      reviews.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      return HttpResponse.json(
        makeReview(
          {},
          {
            version_id: CANDIDATE_ID,
            state: 'in_review',
            revision: candidate.revision,
            base_version_id: BASELINE_ID,
            baseline_version_id: BASELINE_ID,
            story_count: 3,
          },
        ),
      );
    }),
    http.post(APPROVE_URL, async ({ request }) => {
      approvals.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      const reply = approve();
      if (reply.status === 200) {
        outcome = 'approved';
      }
      return reply;
    }),
    http.post(REJECT_URL, async ({ request }) => {
      rejections.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      const reply = reject();
      if (reply.status === 200) {
        outcome = 'rejected';
      }
      return reply;
    }),
  );
  return { reviews, approvals, rejections };
}

function main() {
  return within(screen.getByRole('main'));
}

async function openApproval() {
  await userEvent.click(await main().findByRole('button', { name: 'Approve as v2…' }));
  return within(await screen.findByRole('dialog', { name: 'Approve baseline v2' }));
}

async function openRejection() {
  await userEvent.click(await main().findByRole('button', { name: 'Reject…' }));
  return within(await screen.findByRole('dialog', { name: 'Reject Candidate v2' }));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Approving a change candidate', () => {
  it('checks the scope decision too, approves once on a double click and shows v2 as the baseline', async () => {
    const sent = serveDecision();
    renderApp(PAGE);

    const dialog = await openApproval();

    const checks = within(await dialog.findByRole('list', { name: 'Approval checks' }));
    expect(checks.getAllByRole('listitem')).toHaveLength(5);
    expect(checks.getByText('Scope decision made')).toBeInTheDocument();
    expect(checks.getAllByText('Passed')).toHaveLength(5);
    expect(dialog.getByText(/v1 stays in history, unchanged\./)).toBeVisible();
    expect(dialog.getByText('Revision').nextElementSibling).toHaveTextContent('r2');
    await expectNoAccessibilityViolations();

    await userEvent.dblClick(dialog.getByRole('button', { name: 'Approve as v2' }));

    expect(await main().findByRole('heading', { name: 'Baseline v2' })).toBeVisible();
    expect(sent.approvals).toHaveLength(1);
    expect(sent.approvals[0]?.body).toEqual({
      expected_revision: 2,
      content_hash: REVERSED.content_hash,
      expected_baseline_id: BASELINE_ID,
    });
    expect(sent.approvals[0]?.key).toMatch(/.+/);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(await screen.findByText(/v2 is now the current baseline/)).toBeVisible();
    expect(await main().findByRole('combobox', { name: 'Version' })).toHaveDisplayValue(
      'v2 · current baseline',
    );
    expect(main().queryByRole('button', { name: /Approve|Reject/ })).toBeNull();
  });

  it('keeps Approve disabled until the scope decision is made', async () => {
    serveDecision({ candidate: CANDIDATE });
    renderApp(PAGE);

    const approve = await main().findByRole('button', { name: 'Approve as v2…' });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAccessibleDescription(
      'Approve unlocks once the scope decision below is made.',
    );
    expect(main().getByRole('button', { name: 'Reject…' })).toBeEnabled();
  });

  it('leaves only Reject after a keep decision', async () => {
    serveDecision({ candidate: KEPT });
    renderApp(PAGE);

    expect(await main().findByRole('button', { name: 'Reject…' })).toBeEnabled();
    expect(main().queryByRole('button', { name: /Approve/ })).toBeNull();
    expect(
      main().getByText(/The earlier scope was kept, so this candidate can only be rejected\./),
    ).toBeVisible();
    await expectNoAccessibilityViolations();
  });

  it('asks for a reload and another review when the baseline changed, without retrying', async () => {
    let first = true;
    const sent = serveDecision({
      approve: () => {
        if (first) {
          first = false;
          return HttpResponse.json(
            errorBody('BASELINE_CHANGED', 'Another baseline was approved meanwhile.'),
            { status: 409 },
          );
        }
        return HttpResponse.json(decision('approved'));
      },
    });
    renderApp(PAGE);

    const dialog = await openApproval();
    await dialog.findByRole('list', { name: 'Approval checks' });
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v2' }));

    const alert = await dialog.findByRole('alert');
    expect(alert).toHaveTextContent(
      'This candidate changed after you opened it, or another baseline was approved. Nothing was approved. Another baseline was approved meanwhile.',
    );
    expect(dialog.getByRole('button', { name: 'Approve as v2' })).toBeDisabled();
    expect(sent.approvals).toHaveLength(1);

    await userEvent.click(within(alert).getByRole('button', { name: 'Reload and review again' }));

    await waitFor(() => {
      expect(dialog.queryByRole('alert')).toBeNull();
    });
    expect(sent.reviews.length).toBeGreaterThanOrEqual(2);
    await waitFor(() => {
      expect(dialog.getByRole('button', { name: 'Approve as v2' })).toBeEnabled();
    });
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v2' }));

    expect(await main().findByRole('heading', { name: 'Baseline v2' })).toBeVisible();
    expect(sent.approvals).toHaveLength(2);
    expect(sent.approvals[1]?.key).not.toBe(sent.approvals[0]?.key);
  });

  it('reuses the Idempotency-Key when retrying after an unknown outcome', async () => {
    let first = true;
    const sent = serveDecision({
      approve: () => {
        if (first) {
          first = false;
          return HttpResponse.json(errorBody('INTERNAL', 'Something went wrong.', true), {
            status: 503,
          });
        }
        return HttpResponse.json(decision('approved'));
      },
    });
    renderApp(PAGE);

    const dialog = await openApproval();
    await dialog.findByRole('list', { name: 'Approval checks' });
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v2' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent(
      'The candidate was not approved. Something went wrong. Try again in a moment.',
    );
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v2' }));

    expect(await main().findByRole('heading', { name: 'Baseline v2' })).toBeVisible();
    expect(sent.approvals).toHaveLength(2);
    expect(sent.approvals[1]?.key).toBe(sent.approvals[0]?.key);
  });

  it('offers another review when the server says a scope decision is still needed', async () => {
    serveDecision({
      approve: () =>
        HttpResponse.json(
          {
            ...errorBody('SCOPE_DECISION_REQUIRED', 'A scope decision is still open.'),
            details: { decision_ids: [SCOPE_DECISION_ID] },
          },
          { status: 409 },
        ),
    });
    renderApp(PAGE);

    const dialog = await openApproval();
    await dialog.findByRole('list', { name: 'Approval checks' });
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v2' }));

    const alert = await dialog.findByRole('alert');
    expect(alert).toHaveTextContent(
      'The candidate was not approved. A scope decision is still open.',
    );
    expect(within(alert).getByRole('button', { name: 'Review again' })).toBeVisible();
  });
});

describe('Rejecting a change candidate', () => {
  it('rejects once with the reason on a double click and shows v1 as still current', async () => {
    const sent = serveDecision({ candidate: KEPT });
    renderApp(PAGE);

    const dialog = await openRejection();
    expect(
      dialog.getByText(/Rejecting keeps v1 as the current baseline, unchanged\./),
    ).toBeVisible();
    const reject = dialog.getByRole('button', { name: 'Reject' });
    expect(reject).toBeDisabled();
    await userEvent.type(dialog.getByRole('textbox', { name: 'Reason' }), '  Not this release.  ');
    await expectNoAccessibilityViolations();

    await userEvent.dblClick(reject);

    expect(await main().findByText(/v1 is still the current baseline, unchanged\./)).toBeVisible();
    expect(main().getByRole('heading', { name: 'Candidate v2 · rejected' })).toBeVisible();
    expect(sent.rejections).toHaveLength(1);
    expect(sent.rejections[0]?.body).toEqual({
      expected_revision: KEPT.revision,
      reason: 'Not this release.',
    });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(main().queryByRole('button', { name: /Approve|Reject/ })).toBeNull();
  });

  it('is offered before any scope decision is made', async () => {
    const sent = serveDecision({ candidate: CANDIDATE });
    renderApp(PAGE);

    const dialog = await openRejection();
    await userEvent.type(dialog.getByRole('textbox', { name: 'Reason' }), 'Out of budget.');
    await userEvent.click(dialog.getByRole('button', { name: 'Reject' }));

    await waitFor(() => {
      expect(sent.rejections).toHaveLength(1);
    });
    expect(sent.rejections[0]?.body).toEqual({ expected_revision: 1, reason: 'Out of budget.' });
  });

  it('asks for a reload when the candidate changed meanwhile', async () => {
    serveDecision({
      reject: () =>
        HttpResponse.json(errorBody('VERSION_CHANGED', 'The version changed.'), { status: 409 }),
    });
    renderApp(PAGE);

    const dialog = await openRejection();
    await userEvent.type(dialog.getByRole('textbox', { name: 'Reason' }), 'No.');
    await userEvent.click(dialog.getByRole('button', { name: 'Reject' }));

    const alert = await dialog.findByRole('alert');
    expect(alert).toHaveTextContent('Nothing was rejected. Reload it and review it again.');
    expect(dialog.getByRole('button', { name: 'Reject' })).toBeDisabled();

    await userEvent.click(within(alert).getByRole('button', { name: 'Reload' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });
});

describe('Who may decide a change candidate', () => {
  it('shows anyone but an approver who decides, without the controls', async () => {
    server.use(...candidateHandlers(VIEWER));
    server.use(http.get(CANDIDATE_URL, () => HttpResponse.json(REVERSED)));
    renderApp(PAGE);

    expect(await main().findByText('Approving or rejecting needs a Product owner')).toBeVisible();
    expect(main().queryByRole('button', { name: /Approve|Reject/ })).toBeNull();
  });
});

describe("A change candidate's other open decisions", () => {
  const OPEN_ID = '019a3a5e-0000-7000-8000-00000000030a';
  const OPEN: Schemas['BacklogDecision'] = {
    ...SCOPE_DECISION,
    id: OPEN_ID,
    kind: 'missing_decision',
    subject: 'Waitlist claim window',
    question: 'How long may a waitlisted resident take to accept a freed slot?',
    why_it_matters: 'The request does not say.',
    affected_item_ids: [],
  };
  const WITH_OPEN = { ...REVERSED, decisions: [...REVERSED.decisions, OPEN] };
  const ANSWER_URL = `${API}/backlogs/${CANDIDATE_ID}/candidate-decisions/${OPEN_ID}`;

  it('lets an approver answer one on the candidate, at the revision on screen', async () => {
    serveDecision({ candidate: WITH_OPEN });
    const answers: Sent[] = [];
    server.use(
      http.post(ANSWER_URL, async ({ request }) => {
        answers.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
        return HttpResponse.json({
          ...WITH_OPEN,
          revision: WITH_OPEN.revision + 1,
          decisions: [
            ...REVERSED.decisions,
            { ...OPEN, status: 'answered', answer: 'Two hours.', decided_by: APPROVER_ID },
          ],
        });
      }),
    );
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: 'Answer: Waitlist claim window' }),
    );
    await userEvent.type(main().getByRole('textbox', { name: 'Your answer' }), 'Two hours.');
    await userEvent.click(main().getByRole('button', { name: 'Save answer' }));

    expect(await main().findByText('Two hours.')).toBeVisible();
    expect(answers).toHaveLength(1);
    expect(answers[0]?.body).toEqual({ answer: 'Two hours.', expected_revision: 2 });
    expect(answers[0]?.key).toMatch(/.+/);
  });

  it('shows no answer control to anyone but an approver', async () => {
    server.use(...candidateHandlers(VIEWER));
    server.use(http.get(CANDIDATE_URL, () => HttpResponse.json(WITH_OPEN)));
    renderApp(PAGE);

    expect(await main().findByText('Waitlist claim window')).toBeVisible();
    expect(main().queryByRole('button', { name: /^Answer/ })).toBeNull();
  });
});

describe("A change candidate's agent suggestions", () => {
  const SUGGESTION_ID = '019a3a5e-0000-7000-8000-00000000c901';
  const SUGGESTION = {
    id: SUGGESTION_ID,
    text: 'A series ends after twelve weeks.',
    origin: 'proposed' as const,
    suggestion: 'pending' as const,
    evidence: [],
    confirmed_by: [],
  };
  const SUGGESTING = {
    ...REVERSED,
    items: REVERSED.items.map((item) =>
      item.id === ADDED_STORY.id ? { ...item, criteria: [SUGGESTION] } : item,
    ),
  };
  const REVIEW_URL_FOR = `${API}/backlogs/${CANDIDATE_ID}/candidate-suggestions/${SUGGESTION_ID}`;

  it('lets an approver reject one once, with no undo on a candidate', async () => {
    serveDecision({ candidate: SUGGESTING });
    const reviews: Sent[] = [];
    server.use(
      http.post(REVIEW_URL_FOR, async ({ request }) => {
        reviews.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
        return HttpResponse.json({
          ...SUGGESTING,
          revision: SUGGESTING.revision + 1,
          items: SUGGESTING.items.map((item) =>
            item.id === ADDED_STORY.id
              ? { ...item, criteria: [{ ...SUGGESTION, suggestion: 'rejected' }] }
              : item,
          ),
        });
      }),
    );
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: /^Story.*Book a weekly recurring/ }),
    );
    await userEvent.click(
      await main().findByRole('button', { name: `Reject suggestion: ${SUGGESTION.text}` }),
    );

    expect(await main().findByText('Rejected')).toBeVisible();
    expect(reviews).toHaveLength(1);
    expect(reviews[0]?.body).toEqual({ outcome: 'rejected', expected_revision: 2 });
    expect(main().queryByRole('button', { name: /^Undo rejecting/ })).toBeNull();
  });
});
