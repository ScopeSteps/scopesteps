import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { VIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { SourceBlock, SourceVersion } from './types';

const PROJECT_ID = '019a3a5e-0000-7000-8000-000000000001';
const SOURCES_URL = `*/api/v1/projects/${PROJECT_ID}/sources`;
const PAGE = `/projects/${PROJECT_ID}/sources`;

const BRIEF: SourceVersion = {
  id: '019a3a5e-0000-7000-8000-0000000000b1',
  source_id: '019a3a5e-0000-7000-8000-0000000000a1',
  project_id: PROJECT_ID,
  kind: 'brief',
  version: 1,
  filename: 'brief.md',
  media_type: 'text/markdown',
  checksum_sha256: 'a'.repeat(64),
  word_count: 9,
  block_count: 2,
  created_at: '2026-10-12T09:00:00Z',
};
const TRANSCRIPT: SourceVersion = {
  ...BRIEF,
  id: '019a3a5e-0000-7000-8000-0000000000b2',
  source_id: '019a3a5e-0000-7000-8000-0000000000a2',
  kind: 'transcript',
  filename: 'transcript.txt',
  media_type: 'text/plain',
  block_count: 1,
};
const BRIEF_BLOCKS: SourceBlock[] = [
  {
    id: '019a3a5e-0000-7000-8000-0000000000c1',
    source_version_id: BRIEF.id,
    ordinal: 1,
    text: 'Students book study rooms.',
    locator: { paragraph: 1, start_offset: 0, end_offset: 26 },
  },
  {
    id: '019a3a5e-0000-7000-8000-0000000000c2',
    source_version_id: BRIEF.id,
    ordinal: 2,
    text: 'No recurring bookings <img src=x onerror="alert(1)"> in release one.',
    locator: { paragraph: 2, start_offset: 28, end_offset: 96 },
  },
];
const TRANSCRIPT_BLOCKS: SourceBlock[] = [
  {
    id: '019a3a5e-0000-7000-8000-0000000000c3',
    source_version_id: TRANSCRIPT.id,
    ordinal: 1,
    text: 'Dana: keep it to single slots.',
    locator: { paragraph: 1, start_offset: 0, end_offset: 30 },
  },
];

function errorBody(code: string, message: string, extra: object = {}) {
  return {
    code,
    message,
    request_id: '019a3a5e-1111-7000-8000-000000000000',
    retryable: false,
    details: {},
    ...extra,
  };
}

function serveStoredSources(versions: SourceVersion[] = [BRIEF, TRANSCRIPT]) {
  server.use(
    http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: versions })),
    http.get(`${SOURCES_URL}/${BRIEF.id}/blocks`, () => HttpResponse.json(BRIEF_BLOCKS)),
    http.get(`${SOURCES_URL}/${TRANSCRIPT.id}/blocks`, () => HttpResponse.json(TRANSCRIPT_BLOCKS)),
  );
}

function renderSources(search = '') {
  return renderApp(`${PAGE}${search}`);
}

function main() {
  return within(screen.getByRole('main'));
}

async function openAddSources() {
  await userEvent.click(await main().findByRole('button', { name: 'Add sources' }));
  return within(screen.getByRole('dialog', { name: 'Add sources' }));
}

function chooseFiles() {
  fireEvent.change(screen.getByLabelText('Project brief'), {
    target: { files: [new File(['Students book study rooms.'], 'brief.md')] },
  });
  fireEvent.change(screen.getByLabelText('Meeting transcript'), {
    target: { files: [new File(['Dana: keep it to single slots.'], 'transcript.txt')] },
  });
}

function submitUpload() {
  fireEvent.click(screen.getByRole('button', { name: 'Upload sources' }));
}

const scrollIntoView = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  // jsdom does not implement scrolling.
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
  server.use(...projectHandlers());
});

describe('SourcesView', () => {
  it('lists the stored sources with their kind, size and when they were added', async () => {
    serveStoredSources();

    renderSources();

    expect(main().getByText('Loading sources…')).toBeInTheDocument();
    const table = within(await main().findByRole('table', { name: 'Stored sources' }));
    const rows = table.getAllByRole('row').slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole('cell')
          .map((cell) => cell.textContent),
      ),
    ).toEqual([
      ['v1brief.md', 'Project brief', '2 ¶ · 9 words', expect.any(String)],
      ['v1transcript.txt', 'Meeting transcript', '1 ¶ · 9 words', expect.any(String)],
    ]);
    expect(table.getAllByRole('cell')[3]?.querySelector('time')).toHaveAttribute(
      'datetime',
      BRIEF.created_at,
    );
    expect(await main().findByRole('img', { name: '18 of 6,000 words used' })).toBeInTheDocument();
    expect(
      main().getByText('18 / 6,000 words · TXT or Markdown, up to 512 KB each'),
    ).toBeInTheDocument();
  });

  it('opens a source in the viewer, paragraph by paragraph, and returns focus on close', async () => {
    serveStoredSources();
    const router = renderSources();
    const link = await main().findByRole('link', { name: 'transcript.txt' });

    await userEvent.click(link);

    const viewer = within(screen.getByRole('dialog', { name: 'transcript.txt' }));
    expect(router.state.location.search).toBe(`?version=${TRANSCRIPT.id}`);
    expect(viewer.getByText(/^Meeting transcript · v1 · 9 words · added/)).toBeInTheDocument();
    expect(await viewer.findByText('Dana: keep it to single slots.')).toBeInTheDocument();
    expect(viewer.getByRole('link', { name: 'Paragraph 1' })).toBeInTheDocument();
    expect(screen.queryByText('Students book study rooms.')).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(router.state.location.search).toBe('');
  });

  it('renders source text as text, never as markup', async () => {
    serveStoredSources();

    renderSources(`?version=${BRIEF.id}`);

    expect(
      await screen.findByText(
        'No recurring bookings <img src=x onerror="alert(1)"> in release one.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /x/ })).not.toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });

  it('invites an upload when the project has no sources', async () => {
    serveStoredSources([]);

    renderSources();

    expect(await main().findByRole('heading', { name: 'No sources yet' })).toBeInTheDocument();
    expect(main().getByRole('button', { name: 'Add sources' })).toBeInTheDocument();
  });

  it('moves to the paragraph a link selects', async () => {
    serveStoredSources();
    const selected = BRIEF_BLOCKS[1];

    renderSources(`?version=${BRIEF.id}&block=${selected?.id ?? ''}`);

    const paragraph = (await screen.findByText(/No recurring bookings/)).closest('li');
    expect(paragraph).toHaveAttribute('aria-current', 'true');
    await waitFor(() => {
      expect(paragraph).toHaveFocus();
    });
    expect(scrollIntoView).toHaveBeenCalled();
    expect(screen.getByText('Students book study rooms.').closest('li')).not.toHaveAttribute(
      'aria-current',
    );
  });

  it('opens a superseded version a citation links to, and says it is not current', async () => {
    serveStoredSources([TRANSCRIPT]);

    renderSources(`?version=${BRIEF.id}`);

    const viewer = within(await screen.findByRole('dialog', { name: 'Earlier source version' }));
    expect(await viewer.findByText(/is not the current version of a source/)).toBeInTheDocument();
    expect(await viewer.findByText('Students book study rooms.')).toBeInTheDocument();
  });

  it('says so when the stored sources cannot be loaded, and retries on request', async () => {
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json(errorBody('NOT_FOUND', 'Project not found'), { status: 404 }),
      ),
    );
    renderSources();
    expect(await main().findByRole('alert')).toHaveTextContent(
      'Could not load the stored sources. Project not found',
    );
    serveStoredSources();

    fireEvent.click(main().getByRole('button', { name: 'Try again' }));

    expect(await main().findByRole('link', { name: 'brief.md' })).toBeInTheDocument();
  });

  it('uploads both files in one command, confirms it and lists them', async () => {
    serveStoredSources([]);
    const received: { key: string | null; brief: string; transcript: string }[] = [];
    server.use(
      http.post(SOURCES_URL, async ({ request }) => {
        const form = await request.formData();
        const brief = form.get('brief');
        const transcript = form.get('transcript');
        received.push({
          key: request.headers.get('Idempotency-Key'),
          brief:
            brief !== null && typeof brief !== 'string'
              ? `${brief.name}: ${await brief.text()}`
              : '',
          transcript:
            transcript !== null && typeof transcript !== 'string'
              ? `${transcript.name}: ${await transcript.text()}`
              : '',
        });
        await delay(20);
        serveStoredSources();
        return HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] }, { status: 201 });
      }),
    );
    renderSources();
    await main().findByRole('heading', { name: 'No sources yet' });
    const modal = await openAddSources();
    expect(
      modal.getByText(/up to 512 KB per file and 6,000 words across both/),
    ).toBeInTheDocument();

    chooseFiles();
    submitUpload();

    expect(await screen.findByRole('button', { name: 'Uploading…' })).toBeDisabled();
    expect(
      await screen.findByText('Stored brief.md (version 1) and transcript.txt (version 1).'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Add sources' })).not.toBeInTheDocument();
    expect(received).toHaveLength(1);
    expect(received[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(received[0]?.brief).toBe('brief.md: Students book study rooms.');
    expect(received[0]?.transcript).toBe('transcript.txt: Dana: keep it to single slots.');
    expect(await main().findByRole('link', { name: 'brief.md' })).toBeInTheDocument();
  });

  it('asks for both files before sending anything', async () => {
    serveStoredSources([]);
    let requests = 0;
    server.use(
      http.post(SOURCES_URL, () => {
        requests += 1;
        return HttpResponse.json({ source_versions: [] }, { status: 201 });
      }),
    );
    renderSources();
    await openAddSources();

    submitUpload();

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Choose both a project brief and a meeting transcript.',
    );
    expect(screen.getByLabelText('Project brief')).toBeInvalid();
    expect(requests).toBe(0);
  });

  it('explains a rejected file and marks the input it came from', async () => {
    serveStoredSources([]);
    server.use(
      http.post(SOURCES_URL, () =>
        HttpResponse.json(
          errorBody('UNSUPPORTED_SOURCE_TYPE', 'The transcript must be a .txt or .md file', {
            details: { field: 'transcript', filename: 'transcript.pdf' },
          }),
          { status: 415 },
        ),
      ),
    );
    renderSources();
    await openAddSources();

    chooseFiles();
    submitUpload();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The transcript must be a .txt or .md file');
    expect(screen.getByLabelText('Meeting transcript')).toBeInvalid();
    expect(screen.getByLabelText('Meeting transcript')).toHaveAccessibleDescription(
      'The transcript must be a .txt or .md file',
    );
    expect(screen.getByLabelText('Project brief')).toBeValid();
    expect(screen.getByRole('button', { name: 'Upload sources' })).toBeEnabled();
    await expectNoAccessibilityViolations();
  });

  it('retries a failed upload under the same idempotency key', async () => {
    serveStoredSources([]);
    const keys: (string | null)[] = [];
    server.use(
      http.post(SOURCES_URL, ({ request }) => {
        keys.push(request.headers.get('Idempotency-Key'));
        if (keys.length === 1) {
          return HttpResponse.json(
            errorBody('INTERNAL_ERROR', 'An unexpected error occurred', { retryable: true }),
            { status: 500 },
          );
        }
        return HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT] }, { status: 201 });
      }),
    );
    renderSources();
    await openAddSources();
    chooseFiles();
    submitUpload();
    expect(await screen.findByRole('alert')).toHaveTextContent('An unexpected error occurred');

    submitUpload();

    expect(await screen.findByText(/^Stored brief.md/)).toBeInTheDocument();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it('reports an unreachable API without losing the chosen files', async () => {
    serveStoredSources([]);
    server.use(http.post(SOURCES_URL, () => HttpResponse.error()));
    renderSources();
    await openAddSources();

    chooseFiles();
    submitUpload();

    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not be reached');
    expect(screen.getByRole('button', { name: 'Upload sources' })).toBeEnabled();
    expect(screen.getByRole('dialog', { name: 'Add sources' })).toBeInTheDocument();
  });

  it('offers a viewer no upload', async () => {
    serveStoredSources();
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));

    renderSources();

    await main().findByRole('table', { name: 'Stored sources' });
    await screen.findByRole('button', { name: /Local Reviewer/ });
    expect(screen.queryByRole('button', { name: 'Add sources' })).not.toBeInTheDocument();
  });

  it('has no accessibility violations on the page or with Add sources open', async () => {
    serveStoredSources();
    renderSources();
    await main().findByRole('table', { name: 'Stored sources' });
    await expectNoAccessibilityViolations();

    await openAddSources();

    await expectNoAccessibilityViolations();
  });
});
