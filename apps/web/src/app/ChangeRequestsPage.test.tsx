import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { BACKLOG, errorBody, PROJECT, PROJECT_ID, versionSummary } from '@/test/fixtures';
import { API, projectHandlers, VERSIONS_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const PAGE = `/projects/${PROJECT_ID}/changes`;
const V1_ID = '019a3a5e-0000-7000-8000-0000000000d1';
const V2_ID = '019a3a5e-0000-7000-8000-0000000000d2';
const V3_ID = '019a3a5e-0000-7000-8000-0000000000d3';
const COMPARE_URL = `${VERSIONS_URL}/compare`;

const [EPIC, STORY] = BACKLOG.items;
if (!EPIC || !STORY) {
  throw new Error('The backlog fixture needs an epic and a story.');
}
const ADDED_STORY = {
  ...STORY,
  id: '019a3a5e-0000-7000-8000-000000000103',
  title: 'Book a recurring weekly slot',
  criteria: [],
};
const REMOVED_STORY = {
  ...STORY,
  id: '019a3a5e-0000-7000-8000-000000000104',
  title: 'Print a booking receipt',
  criteria: [],
};
const RENAMED_EPIC = { ...EPIC, title: 'Book and manage study rooms' };
const [OLD_CRITERION] = STORY.criteria;
if (!OLD_CRITERION) {
  throw new Error('The backlog fixture story needs a criterion.');
}

/** What the server reports from v1 to v2: one story added, the epic renamed, one removed. */
const OPERATIONS = [
  {
    kind: 'modify_item',
    item_id: EPIC.id,
    before: EPIC,
    after: RENAMED_EPIC,
    changed_fields: ['title'],
    criteria: [],
  },
  {
    kind: 'add_item',
    item_id: ADDED_STORY.id,
    before: null,
    after: ADDED_STORY,
    changed_fields: [],
    criteria: [],
  },
  {
    kind: 'remove_item',
    item_id: REMOVED_STORY.id,
    before: REMOVED_STORY,
    after: null,
    changed_fields: [],
    criteria: [],
  },
];

const STORY_EDIT = {
  kind: 'modify_item',
  item_id: STORY.id,
  before: STORY,
  after: STORY,
  changed_fields: [],
  criteria: [
    {
      kind: 'modified',
      criterion_id: OLD_CRITERION.id,
      before: OLD_CRITERION,
      after: { ...OLD_CRITERION, text: 'A signed-in user can search rooms by date and time.' },
    },
  ],
};

interface Comparison {
  base: string | null;
  candidate: string | null;
}

function main() {
  return within(screen.getByRole('main'));
}

async function compareSection() {
  return within(await screen.findByRole('region', { name: 'Compare approved versions' }));
}

/**
 * A project whose approved versions are `numbers` (newest first); v2 has the fixture's story,
 * the added story and the renamed epic. Returns the comparisons the page asked the server for.
 */
function serveProject(numbers: number[], operations: unknown[] = OPERATIONS) {
  const ids: Record<number, string> = { 1: V1_ID, 2: V2_ID, 3: V3_ID };
  const latest = numbers[0] ?? null;
  const comparisons: Comparison[] = [];
  server.use(
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        status: {
          state: latest === null ? 'no_baseline' : 'baseline',
          baseline_version: latest,
          baseline_version_id: latest === null ? null : ids[latest],
          open_version_id: null,
        },
      }),
    ),
    http.get(VERSIONS_URL, () =>
      HttpResponse.json({
        versions: numbers.map((number) => versionSummary(ids[number] ?? '', { number })),
        next_cursor: null,
      }),
    ),
    http.get(`${VERSIONS_URL}/${V2_ID}`, () =>
      HttpResponse.json({
        ...BACKLOG,
        id: V2_ID,
        state: 'approved',
        items: [RENAMED_EPIC, STORY, ADDED_STORY],
      }),
    ),
    http.get(`${VERSIONS_URL}/${V1_ID}`, () =>
      HttpResponse.json({
        ...BACKLOG,
        id: V1_ID,
        state: 'approved',
        items: [EPIC, STORY, REMOVED_STORY],
      }),
    ),
    http.get(COMPARE_URL, ({ request }) => {
      const params = new URL(request.url).searchParams;
      const comparison = { base: params.get('base'), candidate: params.get('candidate') };
      comparisons.push(comparison);
      return HttpResponse.json({
        base_version_id: comparison.base,
        base_content_hash: BACKLOG.content_hash,
        candidate_version_id: comparison.candidate,
        candidate_content_hash: BACKLOG.content_hash,
        operations,
      });
    }),
  );
  return comparisons;
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Change requests page', () => {
  it('says change requests start after the first baseline while there is none', async () => {
    serveProject([]);
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'No baseline to change yet' })).toBeVisible();
    expect(screen.getByRole('heading', { level: 1, name: 'Change requests' })).toBeVisible();
    expect(
      within(screen.getByRole('navigation', { name: 'Project' })).getByRole('link', {
        name: 'Change requests',
      }),
    ).toHaveAttribute('aria-current', 'page');
    expect(
      screen.queryByRole('region', { name: 'Compare approved versions' }),
    ).not.toBeInTheDocument();
    expect(main().queryByRole('button')).not.toBeInTheDocument();
  });

  it('lists no change requests and explains that compare needs two approved versions', async () => {
    serveProject([1]);
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'No change requests yet' })).toBeVisible();
    expect(main().getByText(/each compared with v1, the current baseline/)).toBeVisible();
    expect(
      await (
        await compareSection()
      ).findByText('Only v1 is approved so far. Compare needs two approved versions.'),
    ).toBeVisible();
    expect((await compareSection()).queryByRole('combobox')).not.toBeInTheDocument();
  });
});

describe('Comparing approved versions', () => {
  it('shows the server’s added, changed and removed entries and the unchanged count', async () => {
    const comparisons = serveProject([2, 1]);
    renderApp(PAGE);

    const changes = within(
      await (await compareSection()).findByRole('list', { name: 'Changes from v1 to v2' }),
    );
    expect(
      (await compareSection()).getByRole('combobox', { name: 'From version' }),
    ).toHaveDisplayValue('v1');
    expect(
      (await compareSection()).getByRole('combobox', { name: 'To version' }),
    ).toHaveDisplayValue('v2');
    const rows = changes.getAllByRole('listitem');
    expect(rows.map((row) => row.textContent)).toEqual([
      '~ChangedEpicBook and manage study roomsChanged: title. Was “Book a study room”.',
      '+AddedStoryBook a recurring weekly slot',
      '−RemovedStoryPrint a booking receipt',
    ]);
    expect(
      await (await compareSection()).findByText('1 story unchanged between v1 and v2.'),
    ).toBeVisible();
    expect(comparisons).toEqual([{ base: V1_ID, candidate: V2_ID }]);
    await expectNoAccessibilityViolations();
  });

  it('lists each criterion the server reports as changed under its story', async () => {
    serveProject([2, 1], [STORY_EDIT]);
    renderApp(PAGE);

    const criteria = within(
      await (await compareSection()).findByRole('list', { name: 'Acceptance criteria changes' }),
    );
    expect(criteria.getByRole('listitem')).toHaveTextContent(
      '~ChangedA signed-in user can search rooms by date and time.' + `Was “${OLD_CRITERION.text}”`,
    );
    expect(
      await (await compareSection()).findByText('1 story unchanged between v1 and v2.'),
    ).toBeVisible();
  });

  it('asks for two different versions instead of comparing one with itself', async () => {
    const comparisons = serveProject([2, 1]);
    const router = renderApp(PAGE);
    await (await compareSection()).findByRole('list', { name: 'Changes from v1 to v2' });

    await userEvent.selectOptions(
      (await compareSection()).getByRole('combobox', { name: 'From version' }),
      'v2',
    );

    expect((await compareSection()).getByRole('status')).toHaveTextContent(
      'Pick two different versions.',
    );
    expect((await compareSection()).queryByRole('list')).not.toBeInTheDocument();
    expect(comparisons).toHaveLength(1);
    expect(new URLSearchParams(router.state.location.search).get('from')).toBe(V2_ID);
  });

  it('keeps the chosen versions in the URL and compares them in the order chosen', async () => {
    const comparisons = serveProject([3, 2, 1]);
    renderApp(`${PAGE}?from=${V2_ID}&to=${V1_ID}`);

    expect(
      await (await compareSection()).findByRole('list', { name: 'Changes from v2 to v1' }),
    ).toBeVisible();
    expect(comparisons).toEqual([{ base: V2_ID, candidate: V1_ID }]);
  });

  it('falls back to the two newest approved versions when the URL names others', async () => {
    const comparisons = serveProject([2, 1]);
    renderApp(`${PAGE}?from=not-a-version&to=${V3_ID}`);

    await (await compareSection()).findByRole('list', { name: 'Changes from v1 to v2' });
    expect(comparisons).toEqual([{ base: V1_ID, candidate: V2_ID }]);
  });

  it('says so when nothing changed between the two versions', async () => {
    serveProject([2, 1], []);
    renderApp(PAGE);

    expect(await (await compareSection()).findByText('No differences.')).toBeVisible();
    expect(
      await (await compareSection()).findByText('2 stories unchanged between v1 and v2.'),
    ).toBeVisible();
  });

  it('shows the server’s error when the comparison fails, and tries again on request', async () => {
    serveProject([2, 1]);
    let failures = 1;
    server.use(
      http.get(COMPARE_URL, ({ request }) => {
        if (failures > 0) {
          failures -= 1;
          return HttpResponse.json(errorBody('NOT_FOUND', 'No such backlog version.'), {
            status: 404,
          });
        }
        const params = new URL(request.url).searchParams;
        return HttpResponse.json({
          base_version_id: params.get('base'),
          base_content_hash: BACKLOG.content_hash,
          candidate_version_id: params.get('candidate'),
          candidate_content_hash: BACKLOG.content_hash,
          operations: OPERATIONS,
        });
      }),
    );
    renderApp(PAGE);

    const section = await compareSection();
    expect(await section.findByRole('alert')).toHaveTextContent(
      'Could not compare v1 with v2. No such backlog version.',
    );

    await userEvent.click(section.getByRole('button', { name: 'Try again' }));

    expect(await section.findByRole('list', { name: 'Changes from v1 to v2' })).toBeVisible();
    expect(section.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the server’s error when the approved versions cannot be listed', async () => {
    serveProject([2, 1]);
    server.use(
      http.get(VERSIONS_URL, () =>
        HttpResponse.json(errorBody('INTERNAL', 'Something went wrong.', true), { status: 500 }),
      ),
    );
    renderApp(PAGE);

    expect(await (await compareSection()).findByRole('alert')).toHaveTextContent(
      'Could not list the approved versions. Something went wrong.',
    );
    expect((await compareSection()).getByRole('button', { name: 'Try again' })).toBeVisible();
  });
});
