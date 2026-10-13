import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';

import { BacklogView } from '@/features/backlog';
import {
  BACKLOG,
  BRIEF,
  BRIEF_BLOCKS,
  CANCEL_ANSWER,
  CONFIRMED_ID,
  errorBody,
  PROJECT_ID,
  REVIEWER,
  SOURCED_ID,
  TRANSCRIPT,
  TRANSCRIPT_BLOCKS,
  VERSION_ID,
} from '@/test/fixtures';
import { server } from '@/test/server';

const SOURCES_URL = `*/api/v1/projects/${PROJECT_ID}/sources`;
const BACKLOG_URL = `*/api/v1/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const STORY = 'Search for and book a one-off slot';
const SEARCH = 'A signed-in user can search rooms by date, time and capacity.';
const CANCEL = 'A user can cancel their booking up to one hour before it starts.';
const CONFIRMATION = 'After booking, the user sees a confirmation with the room and time.';

let blockRequests: string[] = [];

function renderBacklog(search = '') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/backlog${search}`]}>
        <BacklogView projectId={PROJECT_ID} versionId={VERSION_ID} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function criterion(text: string) {
  const item = screen.getByText(text).closest('li');
  if (!item) {
    throw new Error(`No criterion row for: ${text}`);
  }
  return within(item);
}

beforeEach(() => {
  blockRequests = [];
  server.use(
    http.get('*/api/v1/me', () => HttpResponse.json(REVIEWER)),
    http.get(BACKLOG_URL, () => HttpResponse.json(BACKLOG)),
    http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] })),
    http.get(`${SOURCES_URL}/:versionId/blocks`, ({ params }) => {
      blockRequests.push(String(params.versionId));
      return HttpResponse.json(params.versionId === BRIEF.id ? BRIEF_BLOCKS : TRANSCRIPT_BLOCKS);
    }),
  );
});

describe('BacklogView', () => {
  it('shows epics, stories and criteria, and says the draft is not approved', async () => {
    renderBacklog();

    expect(screen.getByText('Loading the backlog…')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Epic Book a study room' })).toBeVisible();
    const story = within(screen.getByRole('article', { name: `Story ${STORY}` }));
    expect(story.getByText(/As a signed-in user, I want to book a one-off slot/)).toBeVisible();
    expect(
      within(story.getByRole('list', { name: `Acceptance criteria for ${STORY}` })).getAllByRole(
        'listitem',
      ),
    ).toHaveLength(3);
    expect(screen.getByText('Draft: not approved')).toBeInTheDocument();
    expect(screen.getByText(/1 epic, 1 story/)).toBeInTheDocument();
    expect(screen.getByText(`Version ${VERSION_ID}`)).toBeInTheDocument();
  });

  it('labels each claim as source-backed, reviewer-confirmed or AI-proposed', async () => {
    renderBacklog();
    await screen.findByText(SEARCH);

    expect(criterion(SEARCH).getByText('Source-backed')).toBeInTheDocument();
    expect(criterion(CANCEL).getByText('Reviewer-confirmed')).toBeInTheDocument();
    const proposed = criterion(CONFIRMATION);
    expect(proposed.getByText('AI-proposed: needs review')).toBeInTheDocument();
    expect(proposed.getByText('No evidence')).toBeInTheDocument();
    expect(proposed.queryByRole('button')).not.toBeInTheDocument();
  });

  it('labels assumptions and blockers and counts the stories that cannot be approved', async () => {
    renderBacklog();

    const blockers = within(await screen.findByRole('list', { name: `Blockers for ${STORY}` }));
    expect(blockers.getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Blocker: Sources conflict and the question was skipped: Maximum booking length',
      'Blocker: An AI-proposed criterion has not been reviewed',
    ]);
    expect(
      within(screen.getByRole('list', { name: `Assumptions for ${STORY}` })).getByRole('listitem'),
    ).toHaveTextContent('Assumption: Rooms are the group-study rooms in the library.');
    expect(screen.getByText('1 of 1 stories cannot be approved yet.')).toBeInTheDocument();
  });

  it('opens a citation on the exact source version and paragraph', async () => {
    renderBacklog();
    await screen.findByText(SEARCH);

    fireEvent.click(screen.getByRole('button', { name: `Show evidence (1) for: ${SEARCH}` }));

    const drawer = within(screen.getByRole('complementary', { name: 'Evidence' }));
    expect(drawer.getByRole('heading', { name: 'Evidence' })).toHaveFocus();
    expect(drawer.getByText('Acceptance criterion')).toBeInTheDocument();
    expect(drawer.getByText('Source-backed')).toBeInTheDocument();
    expect(await drawer.findByText('Project brief: brief.md, version 1')).toBeInTheDocument();
    expect(drawer.getByText(/Paragraph 2/)).toBeInTheDocument();
    const quoted = drawer.getByText('search rooms by date, time and capacity');
    expect(quoted.tagName).toBe('MARK');
    expect(quoted.closest('blockquote')).toHaveTextContent(BRIEF_BLOCKS[1]?.text ?? '');
    expect(drawer.getByRole('link', { name: 'Open in Sources' })).toHaveAttribute(
      'href',
      `/projects/${PROJECT_ID}/sources?version=${BRIEF.id}&block=${BRIEF_BLOCKS[1]?.id ?? ''}`,
    );
    expect(blockRequests).toEqual([BRIEF.id]);

    fireEvent.click(drawer.getByRole('button', { name: 'Close evidence' }));

    expect(screen.queryByRole('complementary', { name: 'Evidence' })).not.toBeInTheDocument();
  });

  it('shows who confirmed a reviewer-confirmed criterion and what they answered', async () => {
    renderBacklog();
    await screen.findByText(CANCEL);

    fireEvent.click(screen.getByRole('button', { name: `Show evidence (1) for: ${CANCEL}` }));

    const drawer = within(screen.getByRole('complementary', { name: 'Evidence' }));
    expect(drawer.getByText('Reviewer-confirmed')).toBeInTheDocument();
    const answer = within(
      drawer.getByRole('region', { name: 'Reviewer decision: Cancellation and no-shows' }),
    );
    expect(answer.getByText('How late may a user cancel a booking?')).toBeInTheDocument();
    expect(answer.getByText(CANCEL_ANSWER)).toBeInTheDocument();
    expect(await answer.findByText(/Answered by Local Reviewer/)).toBeInTheDocument();
    expect(blockRequests).toEqual([]);
  });

  it('lists an unresolved conflict with the story it blocks and both conflicting passages', async () => {
    renderBacklog();

    const open = within(await screen.findByRole('region', { name: 'Open decisions (1)' }));
    expect(open.getByText('Conflict: skipped, still unresolved')).toBeInTheDocument();
    expect(open.getByText(`Blocks:`).parentElement).toHaveTextContent(`Blocks: ${STORY}`);
    expect(
      await open.findByText(/Skipped by Local Reviewer\. No answer was assumed\./),
    ).toBeVisible();
    expect(screen.getByRole('region', { name: 'Answered by a reviewer (1)' })).toHaveTextContent(
      `Answer by Local Reviewer: ${CANCEL_ANSWER}`,
    );

    fireEvent.click(
      open.getByRole('button', { name: 'Show evidence (2) for: Maximum booking length' }),
    );

    const drawer = within(screen.getByRole('complementary', { name: 'Evidence' }));
    expect(await drawer.findByText('A booking can last up to 4 hours.')).toBeInTheDocument();
    expect(drawer.getAllByText('Conflicting passage')).toHaveLength(2);
    expect(
      await drawer.findByText('Meeting transcript: transcript.md, version 1'),
    ).toBeInTheDocument();
    // The transcript holds markdown emphasis the quote lacks, so the quote is shown beside it.
    expect(
      drawer.getByText('Dana (Facilities): Three hours is the most I want for a single booking.')
        .tagName,
    ).toBe('Q');
    expect(drawer.getByText(/^\*\*Dana \(Facilities\):\*\* Three hours/).tagName).toBe(
      'BLOCKQUOTE',
    );
    expect([...blockRequests].sort()).toEqual([BRIEF.id, TRANSCRIPT.id].sort());
  });

  it('shows excluded work as not in the backlog, with its evidence', async () => {
    renderBacklog();

    const excluded = within(await screen.findByRole('region', { name: 'Not in this backlog' }));
    expect(excluded.getByRole('listitem')).toHaveTextContent(
      'Excluded by the sources: Recurring reservations are out of scope for release one.',
    );
    expect(screen.getByRole('article', { name: `Story ${STORY}` })).not.toHaveTextContent(
      /recurring/i,
    );

    fireEvent.click(excluded.getByRole('button', { name: /^Show evidence \(1\)/ }));

    const drawer = within(screen.getByRole('complementary', { name: 'Evidence' }));
    expect(drawer.getByText('Excluded by the sources')).toBeInTheDocument();
    expect(await drawer.findByText(/Paragraph 2/)).toBeInTheDocument();
    expect(blockRequests).toEqual([TRANSCRIPT.id]);
  });

  it.each([
    [`?evidence=criterion:${SOURCED_ID}`, 'Source-backed'],
    [`?evidence=criterion:${CONFIRMED_ID}`, 'Reviewer-confirmed'],
  ])('restores the open evidence drawer from the URL %s', async (search, origin) => {
    renderBacklog(search);

    const drawer = within(await screen.findByRole('complementary', { name: 'Evidence' }));
    expect(drawer.getByText(origin)).toBeInTheDocument();
  });

  it('closes the drawer with Escape and says when a link matches nothing', async () => {
    renderBacklog('?evidence=criterion:019a3a5e-0000-7000-8000-00000000ffff');

    const drawer = await screen.findByRole('complementary', { name: 'Evidence' });
    expect(within(drawer).getByRole('alert')).toHaveTextContent(
      'This link does not match anything in this backlog version.',
    );

    fireEvent.keyDown(drawer, { key: 'Escape' });

    expect(screen.queryByRole('complementary', { name: 'Evidence' })).not.toBeInTheDocument();
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

    renderBacklog();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not load the backlog. Backlog version not found',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Epic Book a study room' })).toBeInTheDocument();
    });
  });
});
