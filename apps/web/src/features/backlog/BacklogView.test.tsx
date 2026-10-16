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
  CONFIRMED_ID,
  errorBody,
  PROJECT_ID,
  SOURCED_ID,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
  VERSION_ID,
} from '@/test/fixtures';
import { API, projectHandlers, SOURCES_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const BACKLOG_URL = `${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const STORY = 'Search for and book a one-off slot';
const SEARCH = 'A signed-in user can search rooms by date, time and capacity.';
const CANCEL = 'A user can cancel their booking up to one hour before it starts.';
const CONFIRMATION = 'After booking, the user sees a confirmation with the room and time.';

function main() {
  return within(screen.getByRole('main'));
}

function criterion(text: string) {
  const item = screen.getByText(text).closest('li');
  if (!item) {
    throw new Error(`No criterion row for: ${text}`);
  }
  return within(item);
}

function storyToggle() {
  return main().getByRole('button', { name: new RegExp(`^Story ${STORY}`) });
}

function sheet() {
  return within(screen.getByRole('dialog', { name: 'Evidence' }));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    ...projectHandlers(),
    http.get(BACKLOG_URL, () => HttpResponse.json(BACKLOG)),
  );
});

describe('BacklogView', () => {
  it('shows epics, stories and criteria, and says the draft is not approved', async () => {
    renderApp(PAGE);

    expect(main().getByText('Loading the backlog…')).toBeInTheDocument();
    expect(await main().findByRole('heading', { level: 2, name: 'Draft r1' })).toBeVisible();
    expect(
      main().getByText('Draft revision r1. Nothing is final until it’s approved.'),
    ).toBeVisible();
    expect(main().getByText('1 epic, 1 story')).toBeVisible();
    expect(main().getByRole('heading', { level: 4, name: 'Epic Book a study room' })).toBeVisible();
    expect(storyToggle()).toHaveAttribute('aria-expanded', 'true');
    expect(storyToggle()).toHaveTextContent('1 blocked');
    expect(storyToggle()).toHaveTextContent('1 suggestion');
    expect(main().getByText(/As a signed-in user, I want to book a one-off slot/)).toBeVisible();
    expect(
      within(main().getByRole('list', { name: `Acceptance criteria for ${STORY}` })).getAllByRole(
        'listitem',
      ),
    ).toHaveLength(3);
  });

  it('labels each criterion by where it comes from', async () => {
    renderApp(PAGE);
    await screen.findByText(SEARCH);

    expect(criterion(SEARCH).getByText('Source-backed')).toBeInTheDocument();
    expect(criterion(CANCEL).getByText('Confirmed by an answer')).toBeInTheDocument();
    const proposed = criterion(CONFIRMATION);
    expect(proposed.getByText('Agent suggestion · no source')).toBeInTheDocument();
    expect(proposed.getByText('No evidence')).toBeInTheDocument();
    expect(proposed.queryByRole('button', { name: /evidence for/ })).not.toBeInTheDocument();
  });

  it('says what needs attention, with the blockers and assumptions the API returns', async () => {
    renderApp(PAGE);
    await main().findByRole('heading', { name: 'Draft r1' });

    expect(main().getByRole('status')).toHaveTextContent(
      '2 items need attention before approval: 1 blocked by open decisions, 1 agent suggestion to review.',
    );
    const blockers = within(main().getByRole('list', { name: `Blockers for ${STORY}` }));
    expect(blockers.getByRole('listitem')).toHaveTextContent(
      'Sources conflict and the question was skipped: Maximum booking length',
    );
    expect(blockers.getByText('Waiting on a decision')).toBeInTheDocument();
    expect(
      within(main().getByRole('list', { name: `Assumptions for ${STORY}` })).getByRole('listitem'),
    ).toHaveTextContent('Assumption: Rooms are the group-study rooms in the library.');
  });

  it('opens a citation on the exact source version and paragraph, and returns focus on close', async () => {
    const router = renderApp(PAGE);
    const chip = await main().findByRole('button', {
      name: `Brief ¶2, evidence for: ${SEARCH}`,
    });

    await userEvent.click(chip);

    expect(sheet().getByRole('heading', { name: 'Evidence' })).toHaveFocus();
    expect(sheet().getByText('Acceptance criterion')).toBeInTheDocument();
    expect(sheet().getByText('Source-backed')).toBeInTheDocument();
    expect(sheet().getByText('brief.md · Project brief v1 · paragraph 2')).toBeInTheDocument();
    const quoted = sheet().getByText('search rooms by date, time and capacity');
    expect(quoted.tagName).toBe('MARK');
    expect(quoted.closest('blockquote')).toHaveTextContent(BRIEF_BLOCKS[1]?.text ?? '');
    expect(sheet().getByRole('link', { name: 'Open full source' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/sources?version=${BRIEF.id}&block=${BRIEF_BLOCKS[1]?.id ?? ''}`,
    );
    expect(router.state.location.search).toContain(`evidence=criterion%3A${SOURCED_ID}`);
    await expectNoAccessibilityViolations();

    await userEvent.click(sheet().getByRole('button', { name: 'Close' }));

    expect(screen.queryByRole('dialog', { name: 'Evidence' })).not.toBeInTheDocument();
    expect(chip).toHaveFocus();
  });

  it('shows who confirmed a criterion and what they answered', async () => {
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: `Answer, evidence for: ${CANCEL}` }),
    );

    expect(sheet().getByText('Confirmed by an answer')).toBeInTheDocument();
    const answer = within(
      sheet().getByRole('region', { name: 'Reviewer decision: Cancellation and no-shows' }),
    );
    expect(answer.getByText('How late may a user cancel a booking?')).toBeInTheDocument();
    expect(answer.getByText(CANCEL_ANSWER)).toBeInTheDocument();
    expect(await answer.findByText(/Answered by Local Reviewer/)).toBeInTheDocument();
  });

  it('lists the decisions, and an unresolved conflict with both conflicting passages', async () => {
    renderApp(PAGE);

    const decisions = within(await main().findByRole('list', { name: 'Decisions' }));
    const conflict = within(decisions.getByRole('listitem', { name: 'Maximum booking length' }));
    expect(conflict.getByText('Conflict · skipped, still open')).toBeInTheDocument();
    expect(conflict.getByText(`Blocks: ${STORY}`)).toBeInTheDocument();
    expect(
      await conflict.findByText('Skipped by Local Reviewer. No answer was assumed.'),
    ).toBeVisible();
    const answered = within(decisions.getByRole('listitem', { name: 'Cancellation and no-shows' }));
    expect(answered.getByText(CANCEL_ANSWER)).toBeInTheDocument();
    expect(answered.getByText(`Confirms: ${STORY}`)).toBeInTheDocument();

    await userEvent.click(
      await conflict.findByRole('button', {
        name: 'Transcript ¶1, evidence for: Maximum booking length',
      }),
    );

    expect(await sheet().findByText('A booking can last up to 4 hours.')).toBeInTheDocument();
    expect(sheet().getAllByText('Conflicting passage')).toHaveLength(2);
    // The transcript holds markdown emphasis the quote lacks, so the quote is shown beside it.
    expect(
      sheet().getByText('Dana (Facilities): Three hours is the most I want for a single booking.')
        .tagName,
    ).toBe('Q');
    expect(sheet().getByText(/^\*\*Dana \(Facilities\):\*\* Three hours/).tagName).toBe(
      'BLOCKQUOTE',
    );
  });

  it('shows excluded work as out of scope, with its evidence', async () => {
    renderApp(PAGE);

    const excluded = within(await main().findByRole('list', { name: 'Out of scope' }));
    expect(excluded.getByRole('listitem')).toHaveTextContent(
      'Recurring reservations are out of scope for release one.',
    );
    expect(excluded.getByText('Excluded by the sources')).toBeInTheDocument();

    await userEvent.click(await excluded.findByRole('button', { name: /^Transcript ¶2/ }));

    expect(sheet().getByText('Excluded by the sources')).toBeInTheDocument();
    expect(
      await sheet().findByText('transcript.md · Meeting transcript v1 · paragraph 2'),
    ).toBeInTheDocument();
    expect(TRANSCRIPT.id).toBeTruthy();
  });

  it('filters to what needs attention and says when nothing does', async () => {
    server.use(
      http.get(BACKLOG_URL, () =>
        HttpResponse.json({
          ...BACKLOG,
          blockers: [],
          items: BACKLOG.items.map((item) => ({ ...item, blockers: [] })),
          decisions: BACKLOG.decisions.filter((decision) => decision.status === 'answered'),
        }),
      ),
    );
    renderApp(PAGE);
    await main().findByRole('heading', { name: 'Draft r1' });
    expect(storyToggle()).toHaveAttribute('aria-expanded', 'false');

    await userEvent.click(main().getByRole('button', { name: 'Needs attention' }));

    expect(main().getByRole('button', { name: 'Needs attention' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(
      main().queryByRole('button', { name: new RegExp(`^Story ${STORY}`) }),
    ).not.toBeInTheDocument();
    expect(main().queryByRole('list', { name: 'Out of scope' })).not.toBeInTheDocument();
    expect(main().getByText('Nothing here. Everything in this view is resolved.')).toBeVisible();
  });

  it('opens and closes a story from the keyboard', async () => {
    renderApp(PAGE);
    await main().findByRole('heading', { name: 'Draft r1' });

    storyToggle().focus();
    await userEvent.keyboard('{Enter}');

    expect(storyToggle()).toHaveAttribute('aria-expanded', 'false');
    expect(main().queryByText(SEARCH)).not.toBeInTheDocument();

    await userEvent.keyboard(' ');

    expect(storyToggle()).toHaveAttribute('aria-expanded', 'true');
    expect(main().getByText(SEARCH)).toBeVisible();
    await expectNoAccessibilityViolations();
  });

  it.each([
    [`&evidence=criterion:${SOURCED_ID}`, 'Source-backed'],
    [`&evidence=criterion:${CONFIRMED_ID}`, 'Confirmed by an answer'],
  ])('restores the open evidence sheet from the URL %s', async (search, origin) => {
    renderApp(`${PAGE}${search}`);

    expect(await screen.findByRole('dialog', { name: 'Evidence' })).toBeInTheDocument();
    expect(sheet().getByText(origin)).toBeInTheDocument();
  });

  it('closes the sheet with Escape and says when a link matches nothing', async () => {
    const router = renderApp(`${PAGE}&evidence=criterion:019a3a5e-0000-7000-8000-00000000ffff`);

    const dialog = await screen.findByRole('dialog', { name: 'Evidence' });
    expect(within(dialog).getByRole('alert')).toHaveTextContent(
      'This link does not match anything in this backlog version.',
    );

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByRole('dialog', { name: 'Evidence' })).not.toBeInTheDocument();
    expect(router.state.location.search).toBe(`?version=${VERSION_ID}`);
  });

  it('says when the backlog cannot be loaded and loads it on retry', async () => {
    let calls = 0;
    server.use(
      http.get(BACKLOG_URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json(errorBody('NOT_FOUND', 'Backlog version not found'), { status: 404 })
          : HttpResponse.json(BACKLOG);
      }),
    );

    renderApp(PAGE);

    expect(await main().findByRole('alert')).toHaveTextContent(
      'Could not load the backlog. Backlog version not found',
    );
    fireEvent.click(main().getByRole('button', { name: 'Try again' }));

    await waitFor(() => {
      expect(main().getByRole('heading', { name: 'Draft r1' })).toBeInTheDocument();
    });
  });

  it('reads an approved version as read-only, with its content hash', async () => {
    server.use(
      http.get(BACKLOG_URL, () => HttpResponse.json({ ...BACKLOG, state: 'approved' })),
      http.get(`${SOURCES_URL}/:id/blocks`, () => HttpResponse.json(TRANSCRIPT_BLOCKS)),
    );

    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Approved version' })).toBeVisible();
    expect(main().getByText('bbbb…bbbb')).toBeVisible();
    expect(main().queryByRole('group', { name: 'Filter stories' })).not.toBeInTheDocument();
    expect(main().queryByText(/need attention/)).not.toBeInTheDocument();
  });
});
