import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { BACKLOG, errorBody, PROJECT, PROJECT_ID, versionSummary, VIEWER } from '@/test/fixtures';
import { API, projectHandlers, VERSIONS_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import { formatWhen } from './types';

const DRAFT_ID = '019a3a5e-0000-7000-8000-0000000000e3';
const V2_ID = '019a3a5e-0000-7000-8000-0000000000d2';
const V1_ID = '019a3a5e-0000-7000-8000-0000000000d1';
const UNKNOWN_ID = '019a3a5e-0000-7000-8000-0000000000ff';
const PAGE = `/projects/${PROJECT_ID}/backlog`;
const V1_APPROVED_AT = '2026-10-13T15:30:00Z';
const V1_HASH = `a1b2${'0'.repeat(56)}c3d4`;

const HISTORY = [
  versionSummary(DRAFT_ID, { state: 'draft', revision: 3, base_version_id: V2_ID }),
  versionSummary(V2_ID, { number: 2, revision: 2, base_version_id: V1_ID }),
  versionSummary(V1_ID, {
    number: 1,
    content_hash: V1_HASH,
    decision: { decision: 'approved', decided_by: VIEWER.id, decided_at: V1_APPROVED_AT },
  }),
];

function main() {
  return within(screen.getByRole('main'));
}

/**
 * A viewer in a project with baseline v2, v1 before it and draft r3 in progress, each version
 * served by id. Returns the cursors the history was read with.
 */
function serveHistory(pages: (typeof HISTORY)[] = [HISTORY]) {
  const cursors: (string | null)[] = [];
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        roles: ['viewer'],
        status: {
          state: 'draft_in_progress',
          baseline_version: 2,
          baseline_version_id: V2_ID,
          open_version_id: DRAFT_ID,
        },
      }),
    ),
    http.get(`${API}/projects/${PROJECT_ID}/members`, () =>
      HttpResponse.json({
        members: [
          {
            user_id: VIEWER.id,
            display_name: 'Local Approver',
            job_title: '',
            roles: ['approver'],
          },
        ],
      }),
    ),
    http.get(`${VERSIONS_URL}/:versionId`, ({ params }) => {
      switch (params.versionId) {
        case DRAFT_ID:
          return HttpResponse.json({ ...BACKLOG, id: DRAFT_ID, revision: 3 });
        case V2_ID:
          return HttpResponse.json({ ...BACKLOG, id: V2_ID, state: 'approved', revision: 2 });
        case V1_ID:
          return HttpResponse.json({
            ...BACKLOG,
            id: V1_ID,
            state: 'approved',
            content_hash: V1_HASH,
          });
        default:
          return HttpResponse.json(errorBody('NOT_FOUND', 'No such backlog version.'), {
            status: 404,
          });
      }
    }),
    http.get(VERSIONS_URL, ({ request }) => {
      const cursor = new URL(request.url).searchParams.get('cursor');
      cursors.push(cursor);
      const index = cursor === null ? 0 : Number(cursor);
      return HttpResponse.json({
        versions: pages[index],
        next_cursor: index + 1 < pages.length ? String(index + 1) : null,
      });
    }),
  );
  return cursors;
}

async function versionSelect() {
  return main().findByRole('combobox', { name: 'Version' });
}

function optionNames(select: HTMLElement) {
  return within(select)
    .getAllByRole('option')
    .map((option) => option.textContent);
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Backlog version history', () => {
  it('lists every version from the API, newest first, and keeps the chosen one in the URL', async () => {
    serveHistory();
    const router = renderApp(`${PAGE}?version=${V2_ID}`);

    const select = await versionSelect();
    expect(optionNames(select)).toEqual(['Draft r3', 'v2 · current baseline', 'v1']);
    expect(select).toHaveDisplayValue('v2 · current baseline');
    expect(main().getByRole('heading', { name: 'Baseline v2' })).toBeVisible();

    await userEvent.selectOptions(select, 'v1');

    expect(await main().findByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    expect(router.state.location.search).toBe(`?version=${V1_ID}`);
    expect(await versionSelect()).toHaveDisplayValue('v1');
  });

  it('reads a past version read-only, with its approver, approval time and hash', async () => {
    serveHistory();
    renderApp(`${PAGE}?version=${V1_ID}`);

    expect(await main().findByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    const approvedAt = await main().findByText(formatWhen(V1_APPROVED_AT));
    expect(approvedAt).toHaveAttribute('dateTime', V1_APPROVED_AT);
    expect(approvedAt.parentElement).toHaveTextContent(
      `Approved by Local Approver at ${formatWhen(V1_APPROVED_AT)} · a1b2…c3d4 · read-only.`,
    );
    expect(main().getByText('a1b2…c3d4')).toHaveAttribute('title', V1_HASH);
    expect(main().getByText(/read-only\. The current baseline is v2\./)).toBeVisible();
    expect(main().queryByRole('button', { name: /^Edit/ })).not.toBeInTheDocument();
    expect(main().queryByRole('button', { name: /^Approve/ })).not.toBeInTheDocument();
    expect(await screen.findAllByText('v1 · superseded by v2')).toHaveLength(2);
    await expectNoAccessibilityViolations();
  });

  it('names the current baseline in the status chip', async () => {
    serveHistory();
    renderApp(`${PAGE}?version=${V2_ID}`);

    expect(await screen.findAllByText('Baseline v2 approved')).toHaveLength(2);
  });

  it('opens on the draft in progress when the URL names no version', async () => {
    serveHistory();
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Draft r3' })).toBeVisible();
    expect(await versionSelect()).toHaveDisplayValue('Draft r3');
  });

  it('reads the history through every page', async () => {
    const cursors = serveHistory([HISTORY.slice(0, 2), HISTORY.slice(2)]);
    renderApp(`${PAGE}?version=${V2_ID}`);

    await waitFor(async () => {
      expect(optionNames(await versionSelect())).toEqual([
        'Draft r3',
        'v2 · current baseline',
        'v1',
      ]);
    });
    expect(cursors).toEqual([null, '1']);
  });

  it('shows the project’s latest version when the URL names one it does not have', async () => {
    serveHistory();
    const router = renderApp(`${PAGE}?version=${UNKNOWN_ID}`);

    expect(await main().findByRole('heading', { name: 'Draft r3' })).toBeVisible();
    expect(
      main().getByText(
        'The link named a version that isn’t part of this project, so its latest version is shown instead.',
      ),
    ).toBeVisible();
    expect(router.state.location.search).toBe(`?version=${DRAFT_ID}`);

    await userEvent.selectOptions(await versionSelect(), 'v1');

    expect(await main().findByRole('heading', { name: 'Baseline v1' })).toBeVisible();
    expect(main().queryByText(/isn’t part of this project/)).not.toBeInTheDocument();
  });

  it('hides the selector while the project has a single version', async () => {
    serveHistory([[versionSummary(DRAFT_ID, { state: 'draft', revision: 3 })]]);
    renderApp(`${PAGE}?version=${DRAFT_ID}`);

    expect(await main().findByRole('heading', { name: 'Draft r3' })).toBeVisible();
    await waitFor(() => {
      expect(main().queryByRole('combobox', { name: 'Version' })).not.toBeInTheDocument();
    });
  });

  it('keeps the version in view when the history cannot be read, and retries on request', async () => {
    serveHistory();
    let failures = 1;
    server.use(
      http.get(VERSIONS_URL, () => {
        if (failures > 0) {
          failures -= 1;
          return HttpResponse.json(errorBody('INTERNAL', 'Something went wrong.', true), {
            status: 500,
          });
        }
        return HttpResponse.json({ versions: HISTORY, next_cursor: null });
      }),
    );
    renderApp(`${PAGE}?version=${V2_ID}`);

    expect(await main().findByRole('alert')).toHaveTextContent('Could not list the versions.');
    expect(optionNames(await versionSelect())).toEqual(['v2 · current baseline']);

    await userEvent.click(main().getByRole('button', { name: 'Try again' }));

    await waitFor(async () => {
      expect(optionNames(await versionSelect())).toHaveLength(3);
    });
    expect(main().queryByRole('alert')).not.toBeInTheDocument();
  });
});
