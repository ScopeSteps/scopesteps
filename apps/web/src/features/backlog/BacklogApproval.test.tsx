import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  APPROVER,
  BACKLOG,
  errorBody,
  LENGTH_DECISION_ID,
  makeReview,
  PROJECT,
  PROJECT_ID,
  PROPOSED_ID,
  REVIEWER_ID,
  STORY_ID,
  VERSION_ID,
  versionSummary,
} from '@/test/fixtures';
import { API, projectHandlers, VERSIONS_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const BACKLOG_URL = `${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const REVIEW_URL = `${API}/backlogs/${VERSION_ID}/review`;
const APPROVE_URL = `${API}/backlogs/${VERSION_ID}/approve`;
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const READY = {
  ...BACKLOG,
  blockers: [],
  items: BACKLOG.items.map((i) => ({ ...i, blockers: [] })),
};
const APPROVED = { ...READY, state: 'approved' as const };
const DECISION = {
  id: '019a3a5e-0000-7000-8000-000000000401',
  version_id: VERSION_ID,
  decision: 'approved' as const,
  decided_by: REVIEWER_ID,
  revision: 1,
  content_hash: BACKLOG.content_hash,
  decided_at: '2026-10-14T12:00:00Z',
  baseline_version: 1,
  current_baseline_id: VERSION_ID,
};

interface Sent {
  key: string | null;
  body: unknown;
}

/** The draft, the project and the approval endpoints as an approver sees them. */
function serveApproval({
  review = makeReview(),
  approve = () => HttpResponse.json(DECISION),
  draft = READY,
} = {}) {
  let approved = false;
  const reviews: Sent[] = [];
  const approvals: Sent[] = [];
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json(APPROVER)),
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json(
        approved
          ? {
              ...PROJECT,
              roles: ['approver'],
              status: {
                state: 'baseline',
                baseline_version: 1,
                baseline_version_id: VERSION_ID,
                open_version_id: null,
              },
            }
          : {
              ...PROJECT,
              roles: ['approver'],
              status: {
                ...PROJECT.status,
                state: 'draft_in_progress',
                open_version_id: VERSION_ID,
              },
            },
      ),
    ),
    http.get(BACKLOG_URL, () => HttpResponse.json(approved ? APPROVED : draft)),
    http.post(REVIEW_URL, async ({ request }) => {
      reviews.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      return HttpResponse.json(review);
    }),
    http.post(APPROVE_URL, async ({ request }) => {
      approvals.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      const reply = approve();
      if (reply.status === 200) {
        approved = true;
      }
      return reply;
    }),
  );
  return { reviews, approvals };
}

function main() {
  return within(screen.getByRole('main'));
}

function modal() {
  return within(screen.getByRole('dialog', { name: 'Approve baseline v1' }));
}

async function openModal() {
  await userEvent.click(await main().findByRole('button', { name: 'Approve as v1…' }));
  return modal();
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Approving a draft', () => {
  it('shows the server’s checks and what approval binds to, then approves exactly that', async () => {
    const sent = serveApproval();
    renderApp(PAGE);

    const dialog = await openModal();

    expect(dialog.getByRole('heading', { name: 'Approve baseline v1' })).toHaveFocus();
    const checks = within(await dialog.findByRole('list', { name: 'Approval checks' }));
    expect(checks.getAllByRole('listitem')).toHaveLength(4);
    expect(checks.getByText('Every citation resolves')).toBeInTheDocument();
    expect(checks.getAllByText('Passed')).toHaveLength(4);
    expect(dialog.getByText('Revision').nextElementSibling).toHaveTextContent('r1');
    expect(dialog.getByText('Content hash').nextElementSibling).toHaveTextContent('bbbb…bbbb');
    expect(dialog.getByText('Stories').nextElementSibling).toHaveTextContent('1');
    expect(dialog.getByText('Approver').nextElementSibling).toHaveTextContent('Local Approver');
    expect(sent.reviews).toEqual([
      { key: expect.any(String) as string, body: { expected_revision: 1 } },
    ]);
    await expectNoAccessibilityViolations();

    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v1' }));

    expect(await screen.findByText('Baseline v1 saved. It can’t be overwritten.')).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(sent.approvals).toEqual([
      {
        key: expect.any(String) as string,
        body: {
          expected_revision: 1,
          content_hash: BACKLOG.content_hash,
          expected_baseline_id: null,
        },
      },
    ]);
    expect(await main().findByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    expect(main().queryByRole('button', { name: /^Approve/ })).not.toBeInTheDocument();
  });

  it('keeps Approve disabled while a check fails, and names what failed', async () => {
    const review = makeReview({
      suggestions_reviewed: ['criterion 019a3a5e is a pending suggestion'],
      decisions_resolved: Array.from({ length: 10 }, (_, i) => `decision ${String(i)} is open`),
    });
    const decisions = review.checks[3];
    if (decisions) {
      decisions.problem_count = 12;
    }
    const sent = serveApproval({ review });
    renderApp(PAGE);

    const dialog = await openModal();

    const checks = within(await dialog.findByRole('list', { name: 'Approval checks' }));
    expect(checks.getByText('criterion 019a3a5e is a pending suggestion')).toBeInTheDocument();
    expect(checks.getByText('and 2 more')).toBeInTheDocument();
    expect(checks.getByText(/Every agent suggestion is reviewed/)).toHaveTextContent(
      'Every agent suggestion is reviewed: not passed',
    );
    expect(dialog.getByRole('button', { name: 'Approve as v1' })).toBeDisabled();
    expect(sent.approvals).toHaveLength(0);

    await userEvent.click(dialog.getByRole('button', { name: 'Back to review' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(main().getByRole('button', { name: 'Approve as v1…' })).toHaveFocus();
  });

  it('names the story, criterion and decision a failed check is about, not their ids', async () => {
    const review = makeReview({
      suggestions_reviewed: [
        `criterion ${PROPOSED_ID} on item ${STORY_ID} is an unreviewed agent suggestion`,
      ],
      decisions_resolved: [
        `decision ${LENGTH_DECISION_ID} is open`,
        'decision 019a3a5e-0000-7000-8000-0000000009ff is open',
      ],
    });
    const [, , suggestions, decisions] = review.checks;
    if (suggestions && decisions) {
      suggestions.refs = [{ item_id: STORY_ID, criterion_id: PROPOSED_ID, decision_id: null }];
      decisions.refs = [
        { item_id: null, criterion_id: null, decision_id: LENGTH_DECISION_ID },
        { item_id: null, criterion_id: null, decision_id: '019a3a5e-0000-7000-8000-0000000009ff' },
      ];
    }
    const draft = {
      ...READY,
      decisions: READY.decisions.map((d) =>
        d.id === LENGTH_DECISION_ID ? { ...d, status: 'open' as const, decided_by: null } : d,
      ),
    };
    serveApproval({ review, draft });
    renderApp(PAGE);

    const dialog = await openModal();

    const checks = within(await dialog.findByRole('list', { name: 'Approval checks' }));
    expect(
      checks.getByText(
        'Agent suggestion “After booking, the user sees a confirmation with the room…” on story “Search for and book a one-off slot” is not reviewed yet',
      ),
    ).toBeInTheDocument();
    expect(checks.getByText('Decision “Maximum booking length” is still open')).toBeInTheDocument();
    expect(checks.queryByText(new RegExp(PROPOSED_ID))).not.toBeInTheDocument();
    // A decision the version on screen does not hold keeps the server's wording.
    expect(
      checks.getByText('decision 019a3a5e-0000-7000-8000-0000000009ff is open'),
    ).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Approve as v1' })).toBeDisabled();
    await expectNoAccessibilityViolations();
  });

  it('will not approve a draft made before the current baseline', async () => {
    serveApproval({
      review: makeReview({}, { baseline_version_id: '019a3a5e-0000-7000-8000-0000000000e9' }),
    });
    renderApp(PAGE);

    const dialog = await openModal();

    expect(
      await dialog.findByText(/This draft was made before the current baseline was approved/),
    ).toBeVisible();
    expect(dialog.getByRole('button', { name: 'Approve as v1' })).toBeDisabled();
  });

  it('asks for a reload and another review when the draft changed after review, without retrying', async () => {
    let reviewed = 0;
    const sent = serveApproval({
      approve: () =>
        HttpResponse.json(
          errorBody('VERSION_CHANGED', 'The draft changed after it was reviewed.'),
          {
            status: 409,
          },
        ),
    });
    server.use(
      http.post(REVIEW_URL, () => {
        reviewed += 1;
        return HttpResponse.json(makeReview());
      }),
    );
    renderApp(PAGE);

    const dialog = await openModal();
    await dialog.findByRole('list', { name: 'Approval checks' });
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v1' }));

    const alert = await dialog.findByRole('alert');
    expect(alert).toHaveTextContent(
      'This draft changed after you opened it, or another baseline was approved. Nothing was approved. The draft changed after it was reviewed.',
    );
    expect(dialog.getByRole('button', { name: 'Approve as v1' })).toBeDisabled();
    expect(sent.approvals).toHaveLength(1);
    expect(reviewed).toBe(1);

    await userEvent.click(within(alert).getByRole('button', { name: 'Reload and review again' }));

    await waitFor(() => {
      expect(reviewed).toBe(2);
    });
    expect(dialog.queryByRole('alert')).not.toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Approve as v1' })).toBeEnabled();
    expect(sent.approvals).toHaveLength(1);
  });

  it('shows a review that fails on a stale revision as a reason to reload', async () => {
    serveApproval();
    server.use(
      http.post(REVIEW_URL, () =>
        HttpResponse.json(errorBody('VERSION_CHANGED', 'The draft is at revision 2 now.'), {
          status: 409,
        }),
      ),
    );
    renderApp(PAGE);

    const dialog = await openModal();

    expect(await dialog.findByRole('alert')).toHaveTextContent('The draft is at revision 2 now.');
    expect(dialog.getByRole('button', { name: 'Reload and review again' })).toBeVisible();
    expect(dialog.getByRole('button', { name: 'Approve as v1' })).toBeDisabled();
  });

  it('retries a decision that lost a race with the same key, and reports refusals', async () => {
    let calls = 0;
    const sent = serveApproval({
      approve: () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(
              errorBody('DECISION_IN_PROGRESS', 'Another decision is in progress.', true),
              {
                status: 409,
              },
            )
          : HttpResponse.json(errorBody('PERMISSION_DENIED', 'Only an approver can approve.'), {
              status: 403,
            });
      },
    });
    renderApp(PAGE);

    const dialog = await openModal();
    await dialog.findByRole('list', { name: 'Approval checks' });
    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v1' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent(
      'The draft was not approved. Another decision is in progress. Try again in a moment.',
    );

    await userEvent.click(dialog.getByRole('button', { name: 'Approve as v1' }));

    await waitFor(() => {
      expect(dialog.getByRole('alert')).toHaveTextContent(
        'The draft was not approved. Only an approver can approve.',
      );
    });
    expect(sent.approvals).toHaveLength(2);
    expect(sent.approvals[0]?.key).toBe(sent.approvals[1]?.key);
  });

  it('switches between the draft in progress and the current baseline', async () => {
    const baselineId = '019a3a5e-0000-7000-8000-0000000000e0';
    serveApproval();
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({
          ...PROJECT,
          roles: ['approver'],
          status: {
            state: 'draft_in_progress',
            baseline_version: 1,
            baseline_version_id: baselineId,
            open_version_id: VERSION_ID,
          },
        }),
      ),
      http.get(`${API}/projects/${PROJECT_ID}/backlogs/${baselineId}`, () =>
        HttpResponse.json({ ...APPROVED, id: baselineId }),
      ),
      http.get(VERSIONS_URL, () =>
        HttpResponse.json({
          versions: [
            versionSummary(VERSION_ID, { state: 'draft' }),
            versionSummary(baselineId, { number: 1 }),
          ],
          next_cursor: null,
        }),
      ),
    );
    const router = renderApp(PAGE);

    const select = await main().findByRole('combobox', { name: 'Version' });
    expect(
      within(select)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Draft r1', 'v1 · current baseline']);
    expect(main().getByRole('button', { name: 'Approve as v2…' })).toBeVisible();

    await userEvent.selectOptions(select, 'v1 · current baseline');

    expect(await main().findByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    expect(router.state.location.search).toBe(`?version=${baselineId}`);
    expect(main().queryByRole('button', { name: /^Approve/ })).not.toBeInTheDocument();
  });
});
