import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { BACKLOG, BRIEF, PROJECT_ID, VERSION_ID, VIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Version = components['schemas']['BacklogVersionResponse'];
type ItemPatch = components['schemas']['ItemPatchRequest'];

const BACKLOG_URL = `${API}/projects/${PROJECT_ID}/backlogs/${VERSION_ID}`;
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;
const EPIC = 'Book a study room';
const SOURCED_EPIC_ID = '019a3a5e-0000-7000-8000-000000000211';
const PROPOSED_EPIC_ID = '019a3a5e-0000-7000-8000-000000000212';
const ALL_BOOKINGS = 'Library staff see every booking for a day in one list.';
const NO_PHONE = 'Nobody needs to phone the library to book a room.';
const CONTEXT = 'Rooms are often double-booked on the paper sheet.';

function fixtureItem(index: number) {
  const item = BACKLOG.items[index];
  if (!item) {
    throw new Error(`The backlog fixture has no item ${String(index)}`);
  }
  return item;
}

const epicItem = fixtureItem(0);
const storyItem = fixtureItem(1);
const EPIC_ID = epicItem.id;

/** The fixture with criteria on its epic, one of them a pending suggestion, and a story with a
 * second paragraph of context. */
function withEpicCriteria(): Version {
  return {
    ...BACKLOG,
    items: [
      {
        ...epicItem,
        criteria: [
          {
            id: SOURCED_EPIC_ID,
            text: ALL_BOOKINGS,
            origin: 'source',
            evidence: [
              {
                source_version_id: BRIEF.id,
                block_id: '019a3a5e-0000-7000-8000-0000000000c2',
                quote: 'search rooms by date, time and capacity',
                relationship: 'supporting',
              },
            ],
            confirmed_by: [],
          },
          {
            id: PROPOSED_EPIC_ID,
            text: NO_PHONE,
            origin: 'proposed',
            suggestion: 'pending',
            evidence: [],
            confirmed_by: [],
          },
        ],
        blockers: [
          {
            code: 'proposed_criterion',
            message: 'An agent suggestion has not been accepted or rejected',
            item_id: EPIC_ID,
            decision_id: null,
            criterion_id: PROPOSED_EPIC_ID,
          },
        ],
      },
      { ...storyItem, description: `${storyItem.description}\n\n${CONTEXT}` },
    ],
  };
}

function main() {
  return within(screen.getByRole('main'));
}

function epicCriteria() {
  return within(main().getByRole('list', { name: `Acceptance criteria for ${EPIC}` }));
}

function criterion(text: string) {
  const item = screen.getByText(text).closest('li');
  if (!item) {
    throw new Error(`No criterion row for: ${text}`);
  }
  return within(item);
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(
    ...projectHandlers(),
    http.get(BACKLOG_URL, () => HttpResponse.json(withEpicCriteria())),
  );
});

describe('An epic’s acceptance criteria', () => {
  it('are listed on the epic card with their evidence and the suggestion count', async () => {
    renderApp(PAGE);

    const heading = await main().findByRole('heading', {
      level: 4,
      name: /^Epic Book a study room/,
    });
    expect(heading).toHaveTextContent('1 suggestion');
    expect(epicCriteria().getAllByRole('listitem')).toHaveLength(2);
    expect(criterion(ALL_BOOKINGS).getByText('Source-backed')).toBeInTheDocument();
    expect(criterion(NO_PHONE).getByText('Agent suggestion · no source')).toBeInTheDocument();

    await userEvent.click(
      criterion(ALL_BOOKINGS).getByRole('button', {
        name: (name) => name.endsWith(`evidence for: ${ALL_BOOKINGS}`),
      }),
    );
    expect(
      within(await screen.findByRole('dialog', { name: 'Evidence' })).getByText(
        'Acceptance criterion',
      ),
    ).toBeInTheDocument();
  });

  it('let an editor accept a suggestion on the epic itself', async () => {
    const sent: ItemPatch[] = [];
    server.use(
      http.patch(`${API}/backlogs/${VERSION_ID}/items/${EPIC_ID}`, async ({ request }) => {
        sent.push((await request.json()) as ItemPatch);
        return HttpResponse.json(withEpicCriteria());
      }),
    );
    renderApp(PAGE);

    await userEvent.click(
      await main().findByRole('button', { name: `Accept suggestion: ${NO_PHONE}` }),
    );

    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]?.criteria).toEqual([
      { id: SOURCED_EPIC_ID, text: ALL_BOOKINGS, suggestion: null },
      { id: PROPOSED_EPIC_ID, text: NO_PHONE, suggestion: 'accepted' },
    ]);
  });

  it('are read-only for a viewer', async () => {
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));
    renderApp(PAGE);

    expect(await main().findByText(NO_PHONE)).toBeVisible();
    expect(main().queryByRole('button', { name: `Accept suggestion: ${NO_PHONE}` })).toBeNull();
  });

  it('sit beside a story description that keeps its paragraphs', async () => {
    renderApp(PAGE);

    const description = await main().findByText(/Rooms are often double-booked/);
    expect(description).toHaveTextContent(CONTEXT);
    expect(description.textContent).toContain('\n\n');
    expect(description).toHaveClass('whitespace-pre-line');
    await expectNoAccessibilityViolations();
  });
});
