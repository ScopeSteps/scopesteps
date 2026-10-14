import type { components } from '@scopesteps/api-client';
import { cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BACKLOG,
  errorBody,
  LENGTH_DECISION_ID,
  PROJECT_ID,
  PROPOSED_ID,
  REVIEWER,
  REVIEWER_ID,
  SOURCED_ID,
  CONFIRMED_ID,
  STORY_ID,
  VERSION_ID,
  VIEWER,
} from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Version = components['schemas']['BacklogVersionResponse'];
type ItemPatch = components['schemas']['ItemPatchRequest'];
type DecisionAnswer = components['schemas']['DecisionAnswerRequest'];

const BACKLOG_URL = `${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const ITEM_URL = `${API}/backlogs/${VERSION_ID}/items/${STORY_ID}`;
const DECISION_URL = `${API}/backlogs/${VERSION_ID}/decisions/${LENGTH_DECISION_ID}`;
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const STORY = 'Search for and book a one-off slot';
const SEARCH = 'A signed-in user can search rooms by date, time and capacity.';
const CONFIRMATION = 'After booking, the user sees a confirmation with the room and time.';
const ADDED_ID = '019a3a5e-0000-7000-8000-000000000299';

interface Sent<Body> {
  key: string | null;
  body: Body;
}

/**
 * A draft held the way the server holds it: edits and answers apply to it, move its revision and
 * clear the blockers they settle, and every later read returns it.
 */
function serveDraft() {
  let draft: Version = structuredClone(BACKLOG);
  const edits: Sent<ItemPatch>[] = [];
  const answers: Sent<DecisionAnswer>[] = [];
  let reads = 0;

  function settle(next: Version): Version {
    const pendingIds = new Set(
      next.items.flatMap((item) =>
        item.criteria
          .filter(
            (criterion) => criterion.origin === 'proposed' && criterion.suggestion === 'pending',
          )
          .map((criterion) => criterion.id),
      ),
    );
    const open = new Set(
      next.decisions.filter((decision) => decision.status !== 'answered').map((d) => d.id),
    );
    const keep = (blocker: components['schemas']['Blocker']) =>
      blocker.code === 'proposed_criterion'
        ? pendingIds.has(blocker.criterion_id ?? '')
        : open.has(blocker.decision_id ?? '');
    return {
      ...next,
      revision: next.revision + 1,
      content_hash: String(next.revision + 1).padStart(64, 'c'),
      blockers: next.blockers.filter(keep),
      items: next.items.map((item) => ({ ...item, blockers: item.blockers.filter(keep) })),
    };
  }

  server.use(
    http.get(BACKLOG_URL, () => {
      reads += 1;
      return HttpResponse.json(draft);
    }),
    http.patch(ITEM_URL, async ({ request }) => {
      const body = (await request.json()) as ItemPatch;
      edits.push({ key: request.headers.get('Idempotency-Key'), body });
      if (body.expected_revision !== draft.revision) {
        return HttpResponse.json(errorBody('VERSION_CHANGED', 'The draft changed.'), {
          status: 409,
        });
      }
      draft = settle({
        ...draft,
        items: draft.items.map((item) => {
          if (item.id !== STORY_ID) {
            return item;
          }
          const criteria = (body.criteria ?? item.criteria).map((patch) => {
            const old = item.criteria.find((criterion) => criterion.id === patch.id);
            if (!old) {
              return {
                id: ADDED_ID,
                text: patch.text,
                origin: 'person' as const,
                edited_by: REVIEWER_ID,
                evidence: [],
                confirmed_by: [],
              };
            }
            const rewritten = patch.text !== old.text;
            return {
              ...old,
              text: patch.text,
              edited_by: rewritten ? REVIEWER_ID : (old.edited_by ?? null),
              suggestion:
                patch.suggestion ?? (rewritten && old.suggestion ? 'accepted' : old.suggestion),
            };
          });
          const changed =
            (body.title ?? item.title) !== item.title ||
            (body.description ?? item.description) !== item.description ||
            criteria.some((criterion, i) => criterion.text !== item.criteria[i]?.text);
          return {
            ...item,
            title: body.title ?? item.title,
            description: body.description ?? item.description,
            criteria,
            human_edited: item.human_edited || changed,
          };
        }),
      });
      return HttpResponse.json(draft);
    }),
    http.patch(DECISION_URL, async ({ request }) => {
      const body = (await request.json()) as DecisionAnswer;
      answers.push({ key: request.headers.get('Idempotency-Key'), body });
      draft = settle({
        ...draft,
        decisions: draft.decisions.map((decision) =>
          decision.id === LENGTH_DECISION_ID
            ? { ...decision, status: 'answered', answer: body.answer, decided_by: REVIEWER_ID }
            : decision,
        ),
      });
      return HttpResponse.json(draft);
    }),
  );
  return {
    edits,
    answers,
    reads: () => reads,
    current: () => draft,
    /** Another reviewer's edit lands: the revision moves on without this page knowing. */
    changeElsewhere: () => {
      draft = { ...draft, revision: draft.revision + 1 };
    },
  };
}

function main() {
  return within(screen.getByRole('main'));
}

function storyRow() {
  const toggle = main().getByRole('button', { name: new RegExp(`^${STORY}`) });
  const row = toggle.closest('li');
  if (!row) {
    throw new Error('No story row');
  }
  return within(row);
}

function criterion(text: string) {
  const item = main().getByText(text).closest('li');
  if (!item) {
    throw new Error(`No criterion row for: ${text}`);
  }
  return within(item);
}

async function openEditor() {
  await userEvent.click(await main().findByRole('button', { name: `Edit story: ${STORY}` }));
  return within(main().getByRole('form', { name: `Edit story: ${STORY}` }));
}

function reloadPage() {
  cleanup();
  renderApp(PAGE);
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Editing a draft', () => {
  it('saves a story’s title, text and criteria with a new criterion, and keeps them after a refresh', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    const form = await openEditor();
    expect(form.getByRole('textbox', { name: 'Title' })).toHaveFocus();
    await userEvent.clear(form.getByRole('textbox', { name: 'Title' }));
    await userEvent.type(form.getByRole('textbox', { name: 'Title' }), 'Book a one-off room');
    await userEvent.type(form.getByRole('textbox', { name: 'Story' }), ' Even at short notice.');
    const first = form.getByRole('textbox', { name: 'Acceptance criterion 1' });
    await userEvent.clear(first);
    await userEvent.type(first, 'A user can search rooms by date and capacity.');
    await userEvent.click(form.getByRole('button', { name: '+ Add acceptance criterion' }));
    const added = form.getByRole('textbox', { name: 'Acceptance criterion 4' });
    expect(added).toHaveFocus();
    await userEvent.type(added, 'A booking shows in the user’s calendar.');
    await userEvent.click(form.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(main().queryByRole('form')).not.toBeInTheDocument();
    });
    expect(draft.edits).toHaveLength(1);
    expect(draft.edits[0]?.key).toBeTruthy();
    expect(draft.edits[0]?.body).toEqual({
      expected_revision: 1,
      title: 'Book a one-off room',
      description:
        'As a signed-in user, I want to book a one-off slot, so that I can study. Even at short notice.',
      criteria: [
        { id: SOURCED_ID, text: 'A user can search rooms by date and capacity.', suggestion: null },
        { id: CONFIRMED_ID, text: BACKLOG.items[1]?.criteria[1]?.text, suggestion: null },
        { id: PROPOSED_ID, text: CONFIRMATION, suggestion: null },
        { id: null, text: 'A booking shows in the user’s calendar.', suggestion: null },
      ],
    });

    reloadPage();

    expect(await main().findByRole('heading', { name: 'Draft r2' })).toBeVisible();
    const toggle = main().getByRole('button', { name: /^Book a one-off room/ });
    expect(toggle).toHaveTextContent('Edited');
    if (toggle.getAttribute('aria-expanded') !== 'true') {
      await userEvent.click(toggle);
    }
    const edited = criterion('A user can search rooms by date and capacity.');
    expect(edited.getByText('Source-backed')).toBeInTheDocument();
    expect(edited.getByText('Edited')).toBeInTheDocument();
    expect(
      criterion('A booking shows in the user’s calendar.').getByText('Added by a person'),
    ).toBeInTheDocument();
    expect(main().getByText(/Even at short notice\./)).toBeVisible();
  });

  it('accepts a suggestion, then rejects and restores another, sending only its status', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: `Reject suggestion: ${CONFIRMATION}` }),
    );

    const rejected = await waitFor(() => {
      const row = criterion(CONFIRMATION);
      expect(row.getByText('Rejected')).toBeInTheDocument();
      return row;
    });
    expect(main().getByText(CONFIRMATION).tagName).toBe('P');
    expect(main().getByText(CONFIRMATION)).toHaveClass('line-through');
    expect(draft.edits[0]?.body.criteria).toEqual([
      { id: SOURCED_ID, text: SEARCH, suggestion: null },
      { id: CONFIRMED_ID, text: BACKLOG.items[1]?.criteria[1]?.text, suggestion: null },
      { id: PROPOSED_ID, text: CONFIRMATION, suggestion: 'rejected' },
    ]);
    // The row stays open though the story no longer needs attention.
    expect(storyRow().getByText(SEARCH)).toBeVisible();

    await userEvent.click(
      rejected.getByRole('button', { name: `Undo rejecting: ${CONFIRMATION}` }),
    );
    expect(
      await criterion(CONFIRMATION).findByText('Agent suggestion · no source'),
    ).toBeInTheDocument();
    expect(draft.edits[1]?.body.criteria?.[2]).toEqual({
      id: PROPOSED_ID,
      text: CONFIRMATION,
      suggestion: 'pending',
    });
    expect(draft.edits[1]?.body.expected_revision).toBe(2);

    await userEvent.click(
      criterion(CONFIRMATION).getByRole('button', { name: `Accept suggestion: ${CONFIRMATION}` }),
    );
    expect(await criterion(CONFIRMATION).findByText('Suggestion · accepted')).toBeInTheDocument();
    expect(draft.edits[2]?.body.criteria?.[2]?.suggestion).toBe('accepted');
    expect(new Set(draft.edits.map((edit) => edit.key)).size).toBe(3);
    expect(main().getByRole('status')).toHaveTextContent('1 item needs attention');
  });

  it('answers a skipped decision on the draft, which clears its blocker', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    const blockers = within(await main().findByRole('list', { name: `Blockers for ${STORY}` }));
    await userEvent.click(blockers.getByRole('button', { name: 'Answer: Maximum booking length' }));
    const form = within(blockers.getByRole('form', { name: 'Answer: Maximum booking length' }));
    await userEvent.click(form.getByRole('button', { name: 'Save answer' }));
    expect(form.getByText('Enter an answer.')).toBeInTheDocument();
    expect(draft.answers).toHaveLength(0);

    await userEvent.type(form.getByRole('textbox', { name: 'Your answer' }), 'Three hours.');
    await userEvent.click(form.getByRole('button', { name: 'Save answer' }));

    await waitFor(() => {
      expect(main().queryByRole('list', { name: `Blockers for ${STORY}` })).not.toBeInTheDocument();
    });
    expect(draft.answers).toEqual([
      { key: expect.any(String) as string, body: { expected_revision: 1, answer: 'Three hours.' } },
    ]);
    const decisions = within(main().getByRole('list', { name: 'Decisions' }));
    expect(
      within(decisions.getByRole('listitem', { name: 'Maximum booking length' })).getByText(
        'Three hours.',
      ),
    ).toBeInTheDocument();
  });

  it('keeps the edit and shows the server’s reason when saving fails', async () => {
    serveDraft();
    server.use(
      http.patch(ITEM_URL, () =>
        HttpResponse.json(
          errorBody('ITEM_EDIT_INVALID', 'The edit was not saved: criterion 2 has no text'),
          { status: 422 },
        ),
      ),
    );
    renderApp(PAGE);

    const form = await openEditor();
    await userEvent.type(form.getByRole('textbox', { name: 'Title' }), ' today');
    await userEvent.click(form.getByRole('button', { name: 'Save changes' }));

    expect(await form.findByRole('alert')).toHaveTextContent(
      'The story was not saved. The edit was not saved: criterion 2 has no text',
    );
    expect(form.getByRole('textbox', { name: 'Title' })).toHaveValue(`${STORY} today`);
    expect(form.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  });

  it('retries a save whose outcome is unknown with the same key', async () => {
    const draft = serveDraft();
    let calls = 0;
    const keys: (string | null)[] = [];
    server.use(
      http.patch(ITEM_URL, ({ request }) => {
        calls += 1;
        keys.push(request.headers.get('Idempotency-Key'));
        return calls === 1 ? HttpResponse.error() : HttpResponse.json(draft.current());
      }),
    );
    renderApp(PAGE);

    const form = await openEditor();
    await userEvent.click(form.getByRole('button', { name: 'Save changes' }));
    expect(await form.findByRole('alert')).toHaveTextContent('The server could not be reached');
    await userEvent.click(form.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(main().queryByRole('form')).not.toBeInTheDocument();
    });
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('does not save over another reviewer’s change: it asks for a reload instead of retrying', async () => {
    const draft = serveDraft();
    renderApp(PAGE);

    const form = await openEditor();
    draft.changeElsewhere();
    await userEvent.type(form.getByRole('textbox', { name: 'Title' }), ' today');
    await userEvent.click(form.getByRole('button', { name: 'Save changes' }));

    const banner = await main().findByRole('alert');
    expect(banner).toHaveTextContent(
      'Someone else changed this draft after you opened it. Your change was not saved.',
    );
    expect(draft.edits).toHaveLength(1);
    expect(form.getByRole('button', { name: 'Save changes' })).toBeDisabled();
    const reads = draft.reads();

    await userEvent.click(within(banner).getByRole('button', { name: 'Reload' }));

    expect(await main().findByRole('heading', { name: 'Draft r2' })).toBeVisible();
    expect(draft.reads()).toBe(reads + 1);
    expect(main().queryByRole('form')).not.toBeInTheDocument();
    expect(main().queryByRole('alert')).not.toBeInTheDocument();
    expect(draft.edits).toHaveLength(1);
  });

  it('has no accessibility violations while editing a story and answering a decision', async () => {
    serveDraft();
    renderApp(PAGE);

    await openEditor();
    const decisions = within(main().getByRole('list', { name: 'Decisions' }));
    await userEvent.click(
      decisions.getByRole('button', { name: 'Answer: Maximum booking length' }),
    );

    await expectNoAccessibilityViolations();
  });
});

describe('Who may change a draft', () => {
  it('gives an editor every edit control, and says approval needs a Product owner', async () => {
    serveDraft();
    renderApp(PAGE);

    expect(await main().findByRole('button', { name: `Edit story: ${STORY}` })).toBeVisible();
    expect(await main().findByText('Approval needs a Product owner')).toBeVisible();
    expect(main().queryByRole('button', { name: /^Approve/ })).not.toBeInTheDocument();
  });

  it('shows a viewer the draft read-only', async () => {
    serveDraft();
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));
    renderApp(PAGE);

    await main().findByRole('heading', { name: 'Draft r1' });
    await screen.findByText('Viewer');

    expect(main().queryByRole('button', { name: /^Edit story/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /^Accept suggestion/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /^Reject suggestion/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /^Answer:/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /^Approve/ })).not.toBeInTheDocument();
  });

  it('never offers edits on an approved version, even to an editor', async () => {
    server.use(
      http.get(BACKLOG_URL, () => HttpResponse.json({ ...BACKLOG, state: 'approved' })),
      http.get(`${API}/me`, () =>
        HttpResponse.json({
          ...REVIEWER,
          memberships: [
            { project_id: PROJECT_ID, role: 'editor' },
            { project_id: PROJECT_ID, role: 'approver' },
          ],
        }),
      ),
    );
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Approved version' })).toBeVisible();
    expect(
      main().getByText(/Later changes start a new draft; this version never changes\./),
    ).toBeVisible();
    await userEvent.click(main().getByRole('button', { name: new RegExp(`^${STORY}`) }));
    expect(main().getByText(SEARCH)).toBeVisible();
    expect(main().queryByRole('button', { name: /^Edit story/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /^Accept suggestion/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /^Approve/ })).not.toBeInTheDocument();
    expect(main().queryByText('Approval needs a Product owner')).not.toBeInTheDocument();
  });
});
