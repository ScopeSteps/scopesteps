import type { components } from '@scopesteps/api-client';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { BACKLOG, makeRun, PROJECT_ID, RUN_ID, VERSION_ID } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Item = components['schemas']['BacklogItem'];

const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const AREAS = ['Bookings', 'Rooms', 'Payments', 'Notices', 'Reports'] as const;
const STORIES_PER_EPIC = 8;

function id(n: number): string {
  return `019a3a5e-0000-7000-8000-${n.toString(16).padStart(12, '0')}`;
}

function item(overrides: Partial<Item> & Pick<Item, 'id' | 'kind' | 'title'>): Item {
  return {
    parent_id: null,
    description: '',
    criteria: [],
    assumptions: [],
    open_questions: [],
    blockers: [],
    human_edited: false,
    ...overrides,
  };
}

/** Five epics of eight stories each; story 3 of Payments alone mentions refunds. */
function largeBacklog(): components['schemas']['BacklogVersionResponse'] {
  const items = AREAS.flatMap((area, epicIndex) => {
    const epicId = id(0x1000 + epicIndex);
    return [
      item({ id: epicId, kind: 'epic', title: area, description: `Everything about ${area}.` }),
      ...Array.from({ length: STORIES_PER_EPIC }, (_, storyIndex) =>
        item({
          id: id(0x2000 + epicIndex * 100 + storyIndex),
          kind: 'story',
          parent_id: epicId,
          title: `${area} story ${String(storyIndex + 1)}`,
          description:
            area === 'Payments' && storyIndex === 2
              ? 'As a member, I want a refund for a cancelled booking.'
              : `As a member, I want ${area.toLowerCase()} step ${String(storyIndex + 1)}.`,
        }),
      ),
    ];
  });
  return { ...BACKLOG, items, decisions: [], blockers: [], out_of_scope: [], set_aside: [] };
}

function main() {
  return within(screen.getByRole('main'));
}

function epic(name: string) {
  return main().getByRole('button', { name: `Epic ${name}` });
}

async function search(text: string) {
  const box = main().getByRole('textbox', { name: 'Search stories' });
  await userEvent.clear(box);
  await userEvent.type(box, text);
}

beforeEach(() => {
  server.use(
    ...projectHandlers(),
    http.get(`${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`, () =>
      HttpResponse.json(largeBacklog()),
    ),
    http.get(`${API}/projects/${PROJECT_ID}/threads/counts`, () =>
      HttpResponse.json({ items: [], general_open_threads: 0 }),
    ),
    http.get(`${API}/runs/${RUN_ID}`, () =>
      HttpResponse.json(makeRun({ status: 'ready_for_review' })),
    ),
  );
});

describe('a backlog with five epics and forty stories', () => {
  it('counts the epics and stories and lists each epic with its story count', async () => {
    renderApp(PAGE);

    expect(await main().findByText('5 epics, 40 stories')).toBeVisible();
    for (const area of AREAS) {
      expect(epic(area)).toHaveAttribute('aria-expanded', 'true');
      expect(main().getByRole('list', { name: `Stories in ${area}` }).children).toHaveLength(
        STORIES_PER_EPIC,
      );
    }
    expect(main().getAllByText('8 stories')).toHaveLength(AREAS.length);
  });

  it('collapses an epic to its header and expands it again', async () => {
    renderApp(PAGE);
    await userEvent.click(await main().findByRole('button', { name: 'Epic Rooms' }));

    expect(epic('Rooms')).toHaveAttribute('aria-expanded', 'false');
    expect(main().queryByRole('list', { name: 'Stories in Rooms' })).toBeNull();
    expect(main().queryByText('Everything about Rooms.')).toBeNull();
    expect(main().getByRole('list', { name: 'Stories in Bookings' })).toBeVisible();

    await userEvent.click(epic('Rooms'));

    expect(main().getByRole('list', { name: 'Stories in Rooms' })).toBeVisible();
  });

  it('collapses and expands every epic at once', async () => {
    renderApp(PAGE);
    await userEvent.click(await main().findByRole('button', { name: 'Collapse all epics' }));

    expect(main().queryAllByRole('list', { name: /^Stories in / })).toHaveLength(0);
    for (const area of AREAS) {
      expect(epic(area)).toHaveAttribute('aria-expanded', 'false');
    }

    await userEvent.click(main().getByRole('button', { name: 'Expand all epics' }));

    expect(main().getAllByRole('list', { name: /^Stories in / })).toHaveLength(AREAS.length);
  });

  it('finds stories by words in their text and shows how many match', async () => {
    renderApp(PAGE);
    await main().findByText('5 epics, 40 stories');

    await search('refund');

    expect(main().getByText('1 story matches “refund”.')).toBeVisible();
    const payments = main().getByRole('list', { name: 'Stories in Payments' });
    expect(within(payments).getByRole('button', { name: /^Story Payments story 3/ })).toBeVisible();
    expect(main().getByText('1 of 8 stories')).toBeVisible();
    expect(main().queryByRole('list', { name: 'Stories in Bookings' })).toBeNull();
  });

  it('matches every word in any order and ignores case', async () => {
    renderApp(PAGE);
    await main().findByText('5 epics, 40 stories');

    await search('STEP 2 notices');

    expect(main().getByText('1 story matches “STEP 2 notices”.')).toBeVisible();
    expect(main().getByRole('button', { name: /^Story Notices story 2/ })).toBeVisible();
  });

  it('shows every story of an epic the search names', async () => {
    renderApp(PAGE);
    await main().findByText('5 epics, 40 stories');

    await search('Reports');

    expect(main().getByRole('list', { name: 'Stories in Reports' }).children).toHaveLength(
      STORIES_PER_EPIC,
    );
    expect(main().getByText('8 stories match “Reports”.')).toBeVisible();
  });

  it('opens a collapsed epic while the search finds stories in it', async () => {
    renderApp(PAGE);
    await userEvent.click(await main().findByRole('button', { name: 'Collapse all epics' }));

    await search('refund');

    expect(epic('Payments')).toHaveAttribute('aria-expanded', 'true');
    expect(main().getByRole('list', { name: 'Stories in Payments' })).toBeVisible();
  });

  it('says when nothing matches and comes back when the search is cleared', async () => {
    renderApp(PAGE);
    await main().findByText('5 epics, 40 stories');

    await search('parking');

    expect(main().getByText('No stories match “parking”.')).toBeVisible();
    expect(main().queryAllByRole('list', { name: /^Stories in / })).toHaveLength(0);

    await userEvent.clear(main().getByRole('textbox', { name: 'Search stories' }));

    expect(main().getAllByRole('list', { name: /^Stories in / })).toHaveLength(AREAS.length);
  });

  it('has no accessibility violations expanded, collapsed or searched', async () => {
    renderApp(PAGE);
    await main().findByText('5 epics, 40 stories');
    await expectNoAccessibilityViolations();

    await userEvent.click(epic('Rooms'));
    await expectNoAccessibilityViolations();

    await search('refund');
    await expectNoAccessibilityViolations();
  });
});
