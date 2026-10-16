import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  ADDED_STORY,
  CANDIDATE,
  CANDIDATE_ID,
  CANDIDATE_URL,
  CHANGE_SET_URL,
  CHANGED_STORY,
  candidateHandlers,
  decidedCandidate,
  REMOVED_STORY,
  SCOPE_DECISION_URL,
  UNCHANGED_STORY,
} from '@/test/changeFixtures';
import { APPROVER, errorBody, PROJECT_ID, VIEWER } from '@/test/fixtures';
import { projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const PAGE = `/projects/${PROJECT_ID}/backlog?version=${CANDIDATE_ID}`;
const EXCLUSION = 'Recurring reservations are out of scope for release one.';

function main() {
  return within(screen.getByRole('main'));
}

async function storyRow(title: string) {
  return main().findByRole('button', { name: new RegExp(title) });
}

function scopeCard() {
  return within(main().getByRole('article', { name: /reverse the exclusion|Scope decision/ }));
}

/** Records each scope decision sent, answering with `reply`. */
function recordDecisions(reply: () => Response) {
  const sent: { key: string | null; body: unknown }[] = [];
  server.use(
    http.post(SCOPE_DECISION_URL, async ({ request }) => {
      sent.push({ key: request.headers.get('Idempotency-Key'), body: await request.json() });
      return reply();
    }),
  );
  return sent;
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
  server.use(...candidateHandlers());
});

describe('A change candidate in the backlog', () => {
  it('names the candidate, who proposed it and the baseline it is compared with', async () => {
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Candidate v2 (in review)' })).toBeVisible();
    expect(await main().findByText(/Proposed by CR-3, compared with v1\./)).toBeVisible();
    expect(main().getByText(/v1 stays unchanged unless this is approved/)).toBeVisible();
    expect(await main().findByRole('combobox', { name: 'Version' })).toHaveDisplayValue(
      'Candidate v2 (in review)',
    );
    expect(main().queryByRole('button', { name: /Approve/ })).not.toBeInTheDocument();
  });

  it('tags added, changed and removed stories in text, with stable ids, and leaves the rest alone', async () => {
    renderApp(PAGE);
    await main().findByRole('button', { name: /Book a weekly recurring reservation.*Added/ });

    expect(await storyRow(ADDED_STORY.title)).toHaveTextContent(
      `${ADDED_STORY.id.slice(-8)}${ADDED_STORY.title}+Added`,
    );
    expect(await storyRow(CHANGED_STORY.title)).toHaveTextContent(
      `${CHANGED_STORY.id.slice(-8)}${CHANGED_STORY.title}~Changed`,
    );
    expect(await storyRow(REMOVED_STORY.title)).toHaveTextContent(
      `${REMOVED_STORY.id.slice(-8)}${REMOVED_STORY.title}−Removed`,
    );
    expect(await storyRow(UNCHANGED_STORY.title)).toHaveTextContent(
      `${UNCHANGED_STORY.id.slice(-8)}${UNCHANGED_STORY.title}`,
    );
    expect(await storyRow(UNCHANGED_STORY.title)).not.toHaveTextContent(/Added|Changed|Removed/);
    expect(main().getByText('3 stories', { exact: false })).toBeVisible();
    await expectNoAccessibilityViolations();
  });

  it('shows the exclusion it takes back as removed only if reversed', async () => {
    renderApp(PAGE);

    const scope = within(await main().findByRole('list', { name: 'Out of scope' }));
    expect(scope.getByRole('listitem')).toHaveTextContent(`−Removed if reversed${EXCLUSION}`);
  });

  it('lists only the changes with the Changes only filter', async () => {
    renderApp(PAGE);
    await storyRow(UNCHANGED_STORY.title);

    await userEvent.click(await main().findByRole('button', { name: 'Changes only' }));

    expect(main().queryByRole('button', { name: new RegExp(UNCHANGED_STORY.title) })).toBeNull();
    expect(await storyRow(ADDED_STORY.title)).toBeVisible();
    expect(await storyRow(CHANGED_STORY.title)).toBeVisible();
    expect(await storyRow(REMOVED_STORY.title)).toBeVisible();
    expect(main().getByRole('list', { name: 'Out of scope' })).toHaveTextContent(EXCLUSION);

    await userEvent.click(main().getByRole('button', { name: 'All' }));

    expect(await storyRow(UNCHANGED_STORY.title)).toBeVisible();
  });

  it('shows the server’s error when the change set cannot be read', async () => {
    server.use(
      http.get(CHANGE_SET_URL, () =>
        HttpResponse.json(errorBody('INTERNAL', 'Something went wrong.', false), { status: 500 }),
      ),
    );
    renderApp(PAGE);

    expect(await main().findByRole('alert')).toHaveTextContent(
      'Could not load what this candidate changes. Something went wrong.',
    );
    expect(main().getByRole('button', { name: 'Try again' })).toBeVisible();
  });
});

describe('The scope decision on a candidate', () => {
  it('quotes the earlier exclusion and opens its evidence in the sheet', async () => {
    renderApp(PAGE);

    const card = within(
      await main().findByRole('article', { name: 'Decision needed: reverse the exclusion?' }),
    );
    expect(card.getByRole('list', { name: 'Evidence for the earlier scope' })).toHaveTextContent(
      `“${EXCLUSION}”`,
    );

    await userEvent.click(
      await card.findByRole('button', { name: `Transcript ¶2, evidence for: ${EXCLUSION}` }),
    );

    const sheet = within(await screen.findByRole('dialog', { name: 'Evidence' }));
    expect(sheet.getByText('Recurring reservations')).toBeVisible();
    expect(await sheet.findByText(/Recurring reservations are out of scope/)).toBeVisible();
  });

  it('records an approver’s reverse at the revision on screen and shows the exclusion removed', async () => {
    server.use(...candidateHandlers(APPROVER));
    const sent = recordDecisions(() => HttpResponse.json(decidedCandidate('reverse')));
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: 'Yes, reverse it' }));

    expect(await scopeCard().findByText('Reversed')).toBeVisible();
    expect(scopeCard().getByText(/Decided by Local Approver\. Saved as evidence\./)).toBeVisible();
    expect(sent).toHaveLength(1);
    expect(sent[0]?.body).toEqual({ expected_revision: 1, outcome: 'reverse' });
    expect(sent[0]?.key).toMatch(/.+/);
    const scope = within(main().getByRole('list', { name: 'Out of scope' }));
    expect(scope.getByRole('listitem')).toHaveTextContent(`−Removed${EXCLUSION}`);
    expect(scope.getByRole('listitem')).not.toHaveTextContent('if reversed');
    expect(scope.getByRole('listitem')).toHaveTextContent(
      'A Product owner reversed it, so this change takes it back.',
    );
    expect(scope.getByRole('listitem')).not.toHaveTextContent('only if a Product owner');
  });

  it('records an approver’s keep and shows the exclusion kept', async () => {
    server.use(...candidateHandlers(APPROVER));
    const sent = recordDecisions(() => HttpResponse.json(decidedCandidate('keep')));
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: 'No, keep it' }));

    expect(await scopeCard().findByText('Kept')).toBeVisible();
    expect(sent[0]?.body).toEqual({ expected_revision: 1, outcome: 'keep' });
    const scope = within(main().getByRole('list', { name: 'Out of scope' }));
    expect(scope.getByRole('listitem')).toHaveTextContent(`Kept${EXCLUSION}`);
    expect(scope.getByRole('listitem')).toHaveTextContent('A Product owner kept it excluded.');
  });

  it('tells anyone but an approver who must decide, without the choices', async () => {
    server.use(...candidateHandlers(VIEWER));
    renderApp(PAGE);

    const card = within(
      await main().findByRole('article', { name: 'Decision needed: reverse the exclusion?' }),
    );
    expect(
      card.getByText('Waiting for a Product owner. Your role (Viewer) can’t make scope decisions.'),
    ).toBeVisible();
    expect(card.queryByRole('button', { name: /reverse it|keep it/ })).toBeNull();
    await expectNoAccessibilityViolations();
  });

  it('says someone else changed the candidate on a 409 and reloads it on request', async () => {
    server.use(...candidateHandlers(APPROVER));
    recordDecisions(() =>
      HttpResponse.json(errorBody('VERSION_CHANGED', 'The version changed.'), { status: 409 }),
    );
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: 'Yes, reverse it' }));

    expect(await scopeCard().findByRole('alert')).toHaveTextContent(
      'Someone else changed this candidate after you opened it. Your decision was not saved.',
    );
    expect(scopeCard().getByRole('button', { name: 'Yes, reverse it' })).toBeDisabled();

    server.use(http.get(CANDIDATE_URL, () => HttpResponse.json(decidedCandidate('keep'))));
    await userEvent.click(scopeCard().getByRole('button', { name: 'Reload' }));

    await waitFor(() => {
      expect(scopeCard().getByText('Kept')).toBeVisible();
    });
    expect(scopeCard().queryByRole('alert')).toBeNull();
  });

  it('shows the server’s message when a decision fails for another reason', async () => {
    server.use(...candidateHandlers(APPROVER));
    recordDecisions(() =>
      HttpResponse.json(errorBody('PERMISSION_DENIED', 'Only an approver can decide.'), {
        status: 403,
      }),
    );
    renderApp(PAGE);

    await userEvent.click(await main().findByRole('button', { name: 'No, keep it' }));

    expect(await scopeCard().findByRole('alert')).toHaveTextContent(
      'The decision was not saved. Only an approver can decide.',
    );
    expect(CANDIDATE.decisions[0]?.status).toBe('open');
  });
});
