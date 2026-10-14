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

/** Pretty-printed with a trailing newline, as the server sends it; never reformatted. */
function jsonExport(number: number) {
  return `{\n  "schema_version": "scopesteps.backlog-export.v1",\n  "version": {\n    "number": ${String(number)}\n  }\n}\n`;
}

const MARKDOWN_V2 = '# Study Room Booking · backlog v2\n\n## Epic: Book a room\n';

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
      if (format === 'markdown') {
        return new HttpResponse(MARKDOWN_V2, {
          headers: {
            'Content-Type': 'text/markdown; charset=utf-8',
            'Content-Disposition': `attachment; filename="study-room-booking-backlog-v${String(number)}.md"`,
          },
        });
      }
      return new HttpResponse(jsonExport(number), {
        headers: {
          'Content-Type': 'application/json',
          'Content-Disposition': `attachment; filename="study-room-booking-backlog-v${String(number)}.json"`,
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

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('Exporting an approved version', () => {
  it('lets a viewer preview the server’s JSON exactly as sent, and closes back to Export', async () => {
    const requests = serveExports();
    renderApp(PAGE);

    const dialog = await openExport();

    expect(dialog.getByRole('heading', { name: 'Export v2' })).toHaveFocus();
    expect(await dialog.findByRole('textbox', { name: 'Export content' })).toHaveValue(
      jsonExport(2),
    );
    expect(dialog.getByRole('textbox', { name: 'Export content' })).toHaveAttribute('readonly');
    expect(dialog.getByRole('combobox', { name: 'Version' })).toHaveDisplayValue('v2');
    expect(dialog.getByRole('button', { name: 'JSON' })).toHaveAttribute('aria-pressed', 'true');
    expect(dialog.getByText('study-room-booking-backlog-v2.json')).toBeVisible();
    expect(dialog.queryByText(/Jira/)).not.toBeInTheDocument();
    expect(requests).toEqual([{ versionId: VERSION_ID, format: 'json' }]);
    await expectNoAccessibilityViolations();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(main().getByRole('button', { name: 'Export' })).toHaveFocus();
  });

  it('switches the preview to the server’s Markdown', async () => {
    const requests = serveExports();
    renderApp(PAGE);
    const dialog = await openExport();
    await dialog.findByRole('textbox', { name: 'Export content' });

    await userEvent.click(dialog.getByRole('button', { name: 'Markdown' }));

    await waitFor(() => {
      expect(dialog.getByRole('textbox', { name: 'Export content' })).toHaveValue(MARKDOWN_V2);
    });
    expect(dialog.getByRole('button', { name: 'Markdown' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(dialog.getByText('study-room-booking-backlog-v2.md')).toBeVisible();
    expect(requests.at(-1)).toEqual({ versionId: VERSION_ID, format: 'markdown' });
  });

  it('exports a past approved version chosen in the modal', async () => {
    const requests = serveExports();
    renderApp(PAGE);
    const dialog = await openExport();
    await dialog.findByRole('textbox', { name: 'Export content' });
    const picker = dialog.getByRole('combobox', { name: 'Version' });
    expect(
      within(picker)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['v2', 'v1']);

    await userEvent.selectOptions(picker, 'v1');

    expect(await screen.findByRole('dialog', { name: 'Export v1' })).toBeVisible();
    await waitFor(() => {
      expect(dialog.getByRole('textbox', { name: 'Export content' })).toHaveValue(jsonExport(1));
    });
    expect(requests.at(-1)).toEqual({ versionId: V1_ID, format: 'json' });
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

  it('copies exactly the previewed text and confirms it', async () => {
    const user = userEvent.setup();
    serveExports();
    renderApp(PAGE);
    await user.click(await main().findByRole('button', { name: 'Export' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Export v2' }));
    await dialog.findByRole('textbox', { name: 'Export content' });

    await user.click(dialog.getByRole('button', { name: 'Copy' }));

    expect(await screen.findByText('Copied to clipboard.')).toBeVisible();
    expect(await navigator.clipboard.readText()).toBe(jsonExport(2));
  });

  it.each([
    [
      'refuses',
      () => {
        vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(
          new DOMException('Blocked', 'NotAllowedError'),
        );
      },
    ],
    [
      'is unavailable',
      () => {
        vi.spyOn(navigator, 'clipboard', 'get').mockReturnValue(undefined as unknown as Clipboard);
      },
    ],
  ])('selects the text to copy by hand when the clipboard %s', async (_case, blockClipboard) => {
    const user = userEvent.setup();
    blockClipboard();
    serveExports();
    renderApp(PAGE);
    await user.click(await main().findByRole('button', { name: 'Export' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Export v2' }));
    const preview = await dialog.findByRole<HTMLTextAreaElement>('textbox', {
      name: 'Export content',
    });

    await user.click(dialog.getByRole('button', { name: 'Copy' }));

    expect(
      await dialog.findByText(/The browser blocked copying, so the text is selected/),
    ).toBeVisible();
    expect(preview).toHaveFocus();
    expect(preview.value.slice(preview.selectionStart, preview.selectionEnd)).toBe(jsonExport(2));
    expect(screen.queryByText('Copied to clipboard.')).not.toBeInTheDocument();
  });

  it('downloads the server’s text under the server’s filename', async () => {
    serveExports();
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
    renderApp(PAGE);
    const dialog = await openExport();
    await userEvent.click(dialog.getByRole('button', { name: 'Markdown' }));
    await waitFor(() => {
      expect(dialog.getByRole('textbox', { name: 'Export content' })).toHaveValue(MARKDOWN_V2);
    });

    await userEvent.click(dialog.getByRole('button', { name: 'Download' }));

    expect(saved.name).toBe('study-room-booking-backlog-v2.md');
    expect(saved.href).toBe('blob:export');
    expect(saved.blob?.type).toBe('text/markdown; charset=utf-8');
    expect(await saved.blob?.text()).toBe(MARKDOWN_V2);
  });

  it('keeps the layout still and Copy and Download off while the export loads', async () => {
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
    expect(dialog.getByRole('button', { name: 'Copy' })).toBeDisabled();
    expect(dialog.getByRole('button', { name: 'Download' })).toBeDisabled();
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
        return new HttpResponse(jsonExport(2), {
          headers: { 'Content-Disposition': 'attachment; filename="backlog-v2.json"' },
        });
      }),
    );
    renderApp(PAGE);
    const dialog = await openExport();

    const alert = await dialog.findByRole('alert');
    expect(alert).toHaveTextContent(
      'Could not export this version. The database is not reachable.',
    );
    expect(dialog.getByRole('button', { name: 'Copy' })).toBeDisabled();

    await userEvent.click(within(alert).getByRole('button', { name: 'Try again' }));

    expect(await dialog.findByRole('textbox', { name: 'Export content' })).toHaveValue(
      jsonExport(2),
    );
  });

  it.each([
    [
      403,
      errorBody('PERMISSION_DENIED', 'Your role in this project cannot export it.'),
      'Your role in this project cannot export it.',
    ],
    [
      409,
      errorBody('VERSION_NOT_APPROVED', 'Only approved versions can be exported.'),
      'Only approved versions can be exported.',
    ],
  ])(
    'shows the server’s %i rejection even when the page thinks the version is approved',
    async (status, body, message) => {
      serveExports();
      server.use(
        http.get(`${API}/backlogs/:versionId/export`, () => HttpResponse.json(body, { status })),
      );
      renderApp(PAGE);
      const dialog = await openExport();

      expect(await dialog.findByRole('alert')).toHaveTextContent(message);
      expect(dialog.queryByRole('textbox', { name: 'Export content' })).not.toBeInTheDocument();
      expect(dialog.getByRole('button', { name: 'Download' })).toBeDisabled();
    },
  );

  it('says only approved versions can be exported when the project has none', async () => {
    serveExports({ versions: [summary(DRAFT_ID, null, 'draft')] });
    renderApp(PAGE);

    const dialog = await openExport('Export');

    expect(
      await dialog.findByText('Only approved versions can be exported. Approve a baseline first.'),
    ).toBeVisible();
    expect(dialog.queryByRole('button', { name: 'Copy' })).not.toBeInTheDocument();
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
