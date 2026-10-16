import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  ADDED_STORY,
  CANDIDATE_ID,
  candidateHandlers,
  CHANGED_STORY,
  REMOVED_STORY,
} from '@/test/changeFixtures';
import { BACKLOG, PROJECT_ID, VERSION_ID } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const BACKLOG_URL = `${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const EPIC = 'Book a study room';
const STORY = 'Search for and book a one-off slot';

function main() {
  return within(screen.getByRole('main'));
}

function epicCard(title: string) {
  return within(main().getByRole('region', { name: `Epic ${title}` }));
}

function serve(version: typeof BACKLOG) {
  server.use(http.get(BACKLOG_URL, () => HttpResponse.json(version)));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Epic and story labels in the backlog', () => {
  it('puts epics and stories, decisions and out of scope under headings with their counts', async () => {
    serve(BACKLOG);
    renderApp(PAGE);

    expect(
      await main().findByRole('heading', { level: 3, name: 'Epics and stories 1' }),
    ).toBeVisible();
    expect(main().getByRole('heading', { level: 3, name: 'Decisions 2' })).toBeVisible();
    expect(main().getByRole('heading', { level: 3, name: 'Out of scope 1' })).toBeVisible();
    await expectNoAccessibilityViolations();
  });

  it('shows each epic as a card with an Epic tag, its description and story count', async () => {
    serve(BACKLOG);
    renderApp(PAGE);

    expect(await main().findByRole('heading', { level: 4, name: `Epic ${EPIC}` })).toBeVisible();
    const card = epicCard(EPIC);
    expect(card.getByText('Epic')).toBeVisible();
    expect(card.getByText('Students and staff book library study rooms themselves.')).toBeVisible();
    expect(card.getByText('1 story')).toHaveClass('font-mono', 'tabular-nums');
  });

  it('nests each story in its epic with a Story tag in its accessible name', async () => {
    serve(BACKLOG);
    renderApp(PAGE);

    const stories = within(await main().findByRole('list', { name: `Stories in ${EPIC}` }));
    const toggle = stories.getByRole('button', { name: new RegExp(`^Story ${STORY}`) });
    expect(within(toggle).getByText('Story')).toBeVisible();
    expect(stories.getByRole('heading', { level: 5, name: new RegExp(`^Story ${STORY}`) })).toBe(
      toggle.parentElement,
    );
  });

  it('labels an approved version the same way', async () => {
    serve({ ...BACKLOG, state: 'approved', blockers: [] });
    renderApp(PAGE);

    expect(await main().findByRole('heading', { level: 4, name: `Epic ${EPIC}` })).toBeVisible();
    expect(epicCard(EPIC).getByText('1 story')).toBeVisible();
    expect(
      epicCard(EPIC).getByRole('button', { name: new RegExp(`^Story ${STORY}`) }),
    ).toBeVisible();
  });

  it('says when an epic has no stories yet', async () => {
    const epic = BACKLOG.items.filter((item) => item.kind === 'epic');
    serve({ ...BACKLOG, items: epic, blockers: [] });
    renderApp(PAGE);

    expect(await main().findByRole('heading', { level: 4, name: `Epic ${EPIC}` })).toBeVisible();
    expect(epicCard(EPIC).getByText('0 stories')).toBeVisible();
    expect(epicCard(EPIC).getByText('No stories in this epic yet.')).toBeVisible();
    expect(epicCard(EPIC).queryByRole('list')).not.toBeInTheDocument();
  });

  it('tags a candidate’s stories and counts only those a filter leaves', async () => {
    server.use(...candidateHandlers());
    renderApp(`/projects/${PROJECT_ID}/backlog?version=${CANDIDATE_ID}`);

    await main().findByRole('button', { name: new RegExp(`^Story .*${REMOVED_STORY.title}`) });
    expect(epicCard(EPIC).getByText('4 stories')).toBeVisible();

    await userEvent.click(main().getByRole('button', { name: 'Changes only' }));

    const card = epicCard(EPIC);
    expect(card.getByText('3 of 4 stories')).toBeVisible();
    for (const story of [CHANGED_STORY, ADDED_STORY, REMOVED_STORY]) {
      expect(
        card.getByRole('button', { name: new RegExp(`^Story \\w+ ${story.title}`) }),
      ).toBeVisible();
    }
    expect(main().getByRole('heading', { level: 3, name: 'Epics and stories 1' })).toBeVisible();
    await expectNoAccessibilityViolations();
  });
});
