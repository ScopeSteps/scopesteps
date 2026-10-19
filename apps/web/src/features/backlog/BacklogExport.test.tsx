import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import {
  BACKLOG,
  errorBody,
  PROJECT,
  PROJECT_ID,
  VERSION_ID,
  versionSummary,
  VIEWER,
} from '@/test/fixtures';
import { API, projectHandlers, VERSIONS_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

const V1_ID = '019a3a5e-0000-7000-8000-0000000000d1';
const DRAFT_ID = '019a3a5e-0000-7000-8000-0000000000e9';
const PAGE = `/projects/${PROJECT_ID}/backlog?version=${VERSION_ID}`;

function summary(id: string, number: number | null, state: 'approved' | 'draft' = 'approved') {
  return versionSummary(id, { number, state });
}

/** The Jira CSV as the server sends it: CRLF after each row, LF inside quoted cells. */
function csvExport(number: number) {
  return [
    'Issue ID,Issue Type,Summary,Description,Parent',
    '1,Epic,Book a room,Booking study rooms.,',
    `2,Story,"Reserve a slot, v${String(number)}","As a student, I want a slot.\n\nAcceptance criteria\n- One slot at a time.\n- A ""confirmation"" is shown.",1`,
    "3,Story,'=Cancel a booking,,1",
    '',
  ].join('\r\n');
}

const CSV_TYPE = 'text/csv; charset=utf-8; header=present';

interface Request {
  versionId: string;
  format: string | null;
}

/**
 * The viewer looking at baseline v2, with v1 before it, and the export endpoint answering as
 * the server would unless a test replaces it.
 */
function serveExports({ versions = [summary(VERSION_ID, 2), summary(V1_ID, 1)] } = {}) {
  const requests: Request[] = [];
  server.use(
    http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
    http.get(`${API}/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        ...PROJECT,
        roles: ['viewer'],
        status: {
          state: 'baseline',
          baseline_version: 2,
          baseline_version_id: VERSION_ID,
          open_version_id: null,
        },
      }),
    ),
    http.get(`${VERSIONS_URL}/${VERSION_ID}`, () =>
      HttpResponse.json({ ...BACKLOG, state: 'approved' }),
    ),
    http.get(VERSIONS_URL, () => HttpResponse.json({ versions, next_cursor: null })),
    http.get(`${API}/backlogs/:versionId/export`, ({ request, params }) => {
      const format = new URL(request.url).searchParams.get('format');
      const versionId = String(params.versionId);
      requests.push({ versionId, format });
      const number = versionId === V1_ID ? 1 : 2;
      return new HttpResponse(csvExport(number), {
        headers: {
          'Content-Type': CSV_TYPE,
          'Content-Disposition': `attachment; filename="study-room-booking-backlog-v${String(number)}.csv"`,
        },
      });
    }),
  );
  return requests;
}

function main() {
  return within(screen.getByRole('main'));
}

async function openExport(name = 'Export v2') {
  await userEvent.click(await main().findByRole('button', { name: 'Export' }));
  return within(await screen.findByRole('dialog', { name }));
}

/** The preview's rows as ID, Type, Summary and Parent, in the order shown. */
async function previewRows() {
  const table = await screen.findByRole('table', { name: 'Rows of the CSV file' });
  return within(table)
    .getAllByRole('row')
    .slice(1)
    .filter((row) => within(row).queryAllByRole('cell').length > 1)
    .map((row) => {
      const [id = '', type = '', parent = ''] = within(row)
        .getAllByRole('cell')
        .map((cell) => cell.textContent);
      const summary = within(row).getByRole('rowheader').firstElementChild?.textContent ?? '';
      return [id, type, summary, parent];
    });
}

const V2_ROWS = [
  ['1', 'Epic', 'Book a room', ''],
  ['2', 'Story', 'Reserve a slot, v2', '1'],
  ['3', 'Story', "'=Cancel a booking", '1'],
];

/** Captures what the browser is handed to save. */
function catchDownloads() {
  const saved: { blob: Blob | null; name: string; href: string } = {
    blob: null,
    name: '',
    href: '',
  };
  vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
    saved.blob = blob instanceof Blob ? blob : null;
    return 'blob:export';
  });
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.name = this.download;
    saved.href = this.href;
  });
  return saved;
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Exporting an approved version', () => {
  it('lets a viewer preview the server’s CSV as a table, and closes back to Export', async () => {
    const requests = serveExports();
    renderApp(PAGE);

    const dialog = await openExport();

    expect(dialog.getByRole('heading', { name: 'Export v2' })).toHaveFocus();
    expect(await previewRows()).toEqual(V2_ROWS);
    expect(dialog.getByRole('combobox', { name: 'Version' })).toHaveDisplayValue('v2');
    expect(dialog.getByText(/For Jira’s CSV importer/)).toHaveTextContent(
      'Issue ID and Parent keep each story under its epic. Downloads as study-room-booking-backlog-v2.csv.',
    );
    expect(dialog.getByRole('button', { name: 'Download CSV for Jira' })).toBeEnabled();
    for (const gone of ['JSON', 'Markdown', 'Copy', 'Download']) {
      expect(dialog.queryByRole('button', { name: gone })).not.toBeInTheDocument();
    }
    expect(requests).toEqual([{ versionId: VERSION_ID, format: 'csv' }]);
    await expectNoAccessibilityViolations();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(main().getByRole('button', { name: 'Export' })).toHaveFocus();
  });

  it('downloads the server’s file under the server’s name, matching the preview row for row', async () => {
    serveExports();
    const saved = catchDownloads();
    renderApp(PAGE);
    const dialog = await openExport();
    const shown = await previewRows();

    await userEvent.click(dialog.getByRole('button', { name: 'Download CSV for Jira' }));

    expect(saved.name).toBe('study-room-booking-backlog-v2.csv');
    expect(saved.href).toBe('blob:export');
    expect(saved.blob?.type).toBe(CSV_TYPE);
    const text = (await saved.blob?.text()) ?? '';
    expect(text).toBe(csvExport(2));
    const fileRows = text
      .split('\r\n')
      .slice(1, -1)
      .map((line) => line.split(','));
    expect(shown.map((row) => row[0])).toEqual(fileRows.map((cells) => cells[0]));
    expect(shown.map((row) => row[3])).toEqual(fileRows.map((cells) => cells.at(-1)));
  });

  it('shows a row’s description, line breaks and all, when it is expanded', async () => {
    serveExports();
    renderApp(PAGE);
    const dialog = await openExport();
    const table = await dialog.findByRole('table', { name: 'Rows of the CSV file' });
    const story = within(table).getByRole('rowheader', { name: /Reserve a slot, v2/ });
    const toggle = within(story).getByRole('button', { name: 'Show description' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(dialog.queryByText(/As a student, I want a slot/)).not.toBeInTheDocument();

    await userEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveTextContent('Hide description');
    const description = dialog.getByText(/As a student, I want a slot/);
    expect(description.textContent).toBe(
      'As a student, I want a slot.\n\nAcceptance criteria\n- One slot at a time.\n- A "confirmation" is shown.',
    );
    expect(toggle).toHaveAttribute('aria-controls', description.id);
    expect(
      within(within(table).getByRole('rowheader', { name: /Cancel a booking/ })).queryByRole(
        'button',
      ),
    ).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();

    await userEvent.click(toggle);

    expect(dialog.queryByText(/As a student, I want a slot/)).not.toBeInTheDocument();
  });

  it('exports a past approved version chosen in the modal', async () => {
    const requests = serveExports();
    renderApp(PAGE);
    const dialog = await openExport();
    await previewRows();
    const picker = dialog.getByRole('combobox', { name: 'Version' });
    expect(
      within(picker)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['v2', 'v1']);

    await userEvent.selectOptions(picker, 'v1');

    expect(await screen.findByRole('dialog', { name: 'Export v1' })).toBeVisible();
    expect(await dialog.findByText('Reserve a slot, v1')).toBeVisible();
    expect(dialog.getByText('study-room-booking-backlog-v1.csv')).toBeVisible();
    expect(requests.at(-1)).toEqual({ versionId: V1_ID, format: 'csv' });
  });

  it('lists approved versions only, reading every page of the history', async () => {
    serveExports();
    server.use(
      http.get(VERSIONS_URL, ({ request }) => {
        const cursor = new URL(request.url).searchParams.get('cursor');
        return HttpResponse.json(
          cursor === 'older'
            ? { versions: [summary(V1_ID, 1)], next_cursor: null }
            : {
                versions: [summary(DRAFT_ID, null, 'draft'), summary(VERSION_ID, 2)],
                next_cursor: 'older',
              },
        );
      }),
    );
    renderApp(PAGE);

    const dialog = await openExport();

    const picker = dialog.getByRole('combobox', { name: 'Version' });
    await waitFor(() => {
      expect(
        within(picker)
          .getAllByRole('option')
          .map((option) => option.textContent),
      ).toEqual(['v2', 'v1']);
    });
  });

  it('says so when the approved version has no epics or stories', async () => {
    serveExports();
    server.use(
      http.get(
        `${API}/backlogs/:versionId/export`,
        () =>
          new HttpResponse('Issue ID,Issue Type,Summary,Description,Parent\r\n', {
            headers: {
              'Content-Type': CSV_TYPE,
              'Content-Disposition': 'attachment; filename="backlog-v2.csv"',
            },
          }),
      ),
    );
    renderApp(PAGE);

    const dialog = await openExport();

    expect(
      await dialog.findByText(
        'This version has no epics or stories, so the file holds only its header row.',
      ),
    ).toBeVisible();
    expect(dialog.getByRole('button', { name: 'Download CSV for Jira' })).toBeEnabled();
  });

  it('keeps the layout still and Download off while the export loads', async () => {
    serveExports();
    server.use(
      http.get(`${API}/backlogs/:versionId/export`, async () => {
        await delay('infinite');
        return HttpResponse.json({});
      }),
    );
    renderApp(PAGE);

    const dialog = await openExport();

    expect(dialog.getByRole('status')).toHaveTextContent('Loading the export…');
    expect(dialog.getByRole('button', { name: 'Download CSV for Jira' })).toBeDisabled();
    await expectNoAccessibilityViolations();
  });

  it('shows a failed export with the server’s message and tries again', async () => {
    serveExports();
    let failures = 1;
    server.use(
      http.get(`${API}/backlogs/:versionId/export`, () => {
        if (failures > 0) {
          failures -= 1;
          return HttpResponse.json(
            errorBody('SERVICE_UNAVAILABLE', 'The database is not reachable.', true),
            { status: 503 },
          );
        }
        return new HttpResponse(csvExport(2), {
          headers: { 'Content-Disposition': 'attachment; filename="backlog-v2.csv"' },
        });
      }),
    );
    renderApp(PAGE);
    const dialog = await openExport();

    const alert = await dialog.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Could not export this version. The database is not reachable.',
    );
    expect(dialog.getByRole('button', { name: 'Download CSV for Jira' })).toBeDisabled();

    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(await previewRows()).toEqual(V2_ROWS);
  });

  it('refuses to preview or download a file that is not the Jira CSV', async () => {
    serveExports();
    server.use(
      http.get(
        `${API}/backlogs/:versionId/export`,
        () =>
          new HttpResponse('<html>Gateway</html>', {
            headers: { 'Content-Disposition': 'attachment; filename="backlog-v2.csv"' },
          }),
      ),
    );
    renderApp(PAGE);

    const dialog = await openExport();

    expect(await dialog.findByRole('alert')).toHaveTextContent(
      'The server sent a file that is not the expected CSV',
    );
    expect(dialog.queryByRole('table')).not.toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Download CSV for Jira' })).toBeDisabled();
  });

  it.each([
    [
      403,
      errorBody('PERMISSION_DENIED', 'Your role in this project cannot export it.'),
      'Your role in this project cannot export it.',
    ],
    [
      409,
      errorBody('VERSION_NOT_APPROVED', 'Only an approved backlog version can be exported.'),
      'Only an approved backlog version can be exported.',
    ],
  ])(
    'shows the server’s %i refusal as given, even when the page thinks the version is approved',
    async (status, body, message) => {
      serveExports();
      server.use(
        http.get(`${API}/backlogs/:versionId/export`, () => HttpResponse.json(body, { status })),
      );
      renderApp(PAGE);
      const dialog = await openExport();

      expect(await dialog.findByRole('alert')).toHaveTextContent(
        `Could not export this version. ${message}`,
      );
      expect(dialog.queryByRole('table')).not.toBeInTheDocument();
      expect(dialog.getByRole('button', { name: 'Download CSV for Jira' })).toBeDisabled();
    },
  );

  it('says only approved versions can be exported when the project has none', async () => {
    serveExports({ versions: [summary(DRAFT_ID, null, 'draft')] });
    renderApp(PAGE);

    const dialog = await openExport('Export');

    expect(
      await dialog.findByText('Only approved versions can be exported. Approve a baseline first.'),
    ).toBeVisible();
    expect(dialog.queryByRole('button', { name: 'Download CSV for Jira' })).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();

    await userEvent.click(dialog.getByRole('button', { name: 'OK' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('is not offered on a draft', async () => {
    serveExports();
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
      http.get(`${VERSIONS_URL}/${VERSION_ID}`, () => HttpResponse.json(BACKLOG)),
    );
    renderApp(PAGE);

    expect(await main().findByRole('heading', { name: 'Draft r1' })).toBeVisible();
    expect(main().queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  });
});
