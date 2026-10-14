import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { delay, http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { APPROVER, PROJECT, VIEWER } from '@/test/fixtures';
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
  source_number: 1,
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
  source_number: 2,
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

async function openAddSource() {
  await userEvent.click(await main().findByRole('button', { name: 'Add source' }));
  return within(screen.getByRole('dialog', { name: 'Add a source' }));
}

function chooseFile(file: File = new File(['Students book study rooms.'], 'brief.md')) {
  fireEvent.change(screen.getByLabelText('Upload a .txt or .md file'), {
    target: { files: [file] },
  });
}

function addSourceDialog() {
  return within(screen.getByRole('dialog', { name: 'Add a source' }));
}

function submitUpload() {
  fireEvent.click(addSourceDialog().getByRole('button', { name: 'Add source' }));
}

interface ReceivedUpload {
  key: string | null;
  parts: string[];
}

/** Records each upload's key and its parts as "kind: filename: text". */
function recordUploads(respond: () => Response): ReceivedUpload[] {
  const received: ReceivedUpload[] = [];
  server.use(
    http.post(SOURCES_URL, async ({ request }) => {
      const form = await request.formData();
      const parts: string[] = [];
      for (const [kind, value] of form.entries()) {
        parts.push(
          typeof value === 'string'
            ? `${kind}: ${value}`
            : `${kind}: ${value.name}: ${await value.text()}`,
        );
      }
      received.push({ key: request.headers.get('Idempotency-Key'), parts });
      return respond();
    }),
  );
  return received;
}

const SUPPORTING: SourceVersion = {
  ...BRIEF,
  id: '019a3a5e-0000-7000-8000-0000000000b3',
  source_id: '019a3a5e-0000-7000-8000-0000000000a3',
  kind: 'supporting_document',
  source_number: 3,
  filename: 'clubs.md',
  word_count: 40,
  block_count: 3,
};

const scrollIntoView = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  // jsdom does not implement scrolling.
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
  server.use(...projectHandlers());
});

describe('SourcesView', () => {
  it('lists each source with its label, name, kind, counts and when it was added', async () => {
    serveStoredSources([BRIEF, { ...TRANSCRIPT, version: 2 }]);

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
      ['SRC-1brief.md', 'Project brief', '2 ¶ · 9 words', expect.any(String)],
      ['SRC-2transcript.txtv2', 'Meeting transcript', '1 ¶ · 9 words', expect.any(String)],
    ]);
    expect(table.getAllByRole('cell')[3]?.querySelector('time')).toHaveAttribute(
      'datetime',
      BRIEF.created_at,
    );
  });

  it('fills the meter against the limits the API returns', async () => {
    serveStoredSources();
    server.use(
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({
          ...PROJECT,
          id: PROJECT_ID,
          limits: { ...PROJECT.limits, source: { max_bytes: 1048576, max_words: 9000 } },
        }),
      ),
    );

    renderSources();

    expect(await main().findByRole('img', { name: '18 of 9,000 words used' })).toBeInTheDocument();
    expect(
      main().getByText('18 / 9,000 words · TXT or Markdown, up to 1 MB each'),
    ).toBeInTheDocument();
  });

  it('opens a source in the viewer, paragraph by paragraph, and returns focus on close', async () => {
    serveStoredSources();
    const router = renderSources();
    const link = await main().findByRole('link', { name: 'transcript.txt' });

    await userEvent.click(link);

    const viewer = within(screen.getByRole('dialog', { name: 'SRC-2 transcript.txt' }));
    expect(router.state.location.search).toBe(`?version=${TRANSCRIPT.id}`);
    expect(viewer.getByText(/^Meeting transcript · v1 · 9 words · added/)).toBeInTheDocument();
    expect(await viewer.findByText('Dana: keep it to single slots.')).toBeInTheDocument();
    expect(viewer.getByRole('link', { name: 'Paragraph 1' })).toBeInTheDocument();
    expect(screen.queryByText('Students book study rooms.')).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(router.state.location.search).toBe('');
    expect(link).toHaveFocus();
  });

  it('numbers paragraphs as the API does, without splitting them again', async () => {
    serveStoredSources();
    server.use(
      http.get(`${SOURCES_URL}/${BRIEF.id}/blocks`, () =>
        HttpResponse.json([
          {
            ...BRIEF_BLOCKS[0],
            ordinal: 4,
            text: 'First line.\n\nStill the same paragraph.',
          },
        ]),
      ),
    );

    renderSources(`?version=${BRIEF.id}`);

    const paragraphs = within(await screen.findByRole('list', { name: 'Paragraphs' }));
    expect(paragraphs.getAllByRole('listitem')).toHaveLength(1);
    expect(paragraphs.getByRole('link', { name: 'Paragraph 4' })).toHaveTextContent('¶4');
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
    expect(main().getByRole('button', { name: 'Add source' })).toBeInTheDocument();
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

  it('opens a superseded version a citation links to, says it is not current and offers no removal', async () => {
    serveStoredSources([TRANSCRIPT]);

    renderSources(`?version=${BRIEF.id}`);

    const viewer = within(await screen.findByRole('dialog', { name: 'Earlier source version' }));
    expect(await viewer.findByText(/is not the current version of a source/)).toBeInTheDocument();
    expect(await viewer.findByText('Students book study rooms.')).toBeInTheDocument();
    expect(viewer.queryByRole('button', { name: 'Remove source' })).not.toBeInTheDocument();
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

  describe('Add a source', () => {
    it('uploads one file as the brief of an empty project, says when it is used and lists it', async () => {
      serveStoredSources([]);
      const received = recordUploads(() => {
        serveStoredSources([BRIEF]);
        return HttpResponse.json({ source_versions: [BRIEF] }, { status: 201 });
      });
      renderSources();
      await main().findByRole('heading', { name: 'No sources yet' });
      const modal = await openAddSource();
      expect(
        modal.getByText(/Up to 512 KB per file and 6,000 words across all sources/),
      ).toBeInTheDocument();
      expect(modal.getByLabelText('Type')).toHaveValue('brief');
      expect(modal.queryByText(/sample/i)).not.toBeInTheDocument();

      chooseFile();
      submitUpload();

      expect(
        await screen.findByText('SRC-1 brief.md added. The agent uses it from the next run.'),
      ).toBeInTheDocument();
      expect(screen.queryByRole('dialog', { name: 'Add a source' })).not.toBeInTheDocument();
      expect(received).toHaveLength(1);
      expect(received[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
      expect(received[0]?.parts).toEqual(['brief: brief.md: Students book study rooms.']);
      expect(await main().findByRole('link', { name: 'brief.md' })).toBeInTheDocument();
    });

    it('stores a file as the kind chosen, suggesting a supporting document once both exist', async () => {
      serveStoredSources();
      const received = recordUploads(() =>
        HttpResponse.json({ source_versions: [SUPPORTING] }, { status: 201 }),
      );
      renderSources();
      await main().findByRole('table', { name: 'Stored sources' });
      const modal = await openAddSource();
      expect(modal.getByLabelText('Type')).toHaveValue('supporting_document');

      await userEvent.selectOptions(modal.getByLabelText('Type'), 'Meeting transcript');
      chooseFile(new File(['Clubs want weekly slots.'], 'clubs.md'));
      submitUpload();

      expect(await screen.findByText(/^SRC-3 clubs.md added/)).toBeInTheDocument();
      expect(received[0]?.parts).toEqual(['transcript: clubs.md: Clubs want weekly slots.']);
    });

    it('says a file is already stored when the API returns the version it holds', async () => {
      serveStoredSources();
      recordUploads(() => HttpResponse.json({ source_versions: [BRIEF] }, { status: 201 }));
      renderSources();
      await main().findByRole('table', { name: 'Stored sources' });
      await openAddSource();

      chooseFile();
      submitUpload();

      expect(
        await screen.findByText('SRC-1 brief.md is already stored with the same content.'),
      ).toBeInTheDocument();
    });

    it.each([
      [
        'a file that is not text or Markdown',
        new File(['%PDF'], 'brief.pdf'),
        'brief.pdf is not a .txt or .md file.',
      ],
      ['an empty file', new File([], 'empty.md'), 'empty.md is empty.'],
      [
        'a file over the size limit',
        new File(['x'.repeat(600)], 'long.md'),
        'long.md is larger than 512 bytes.',
      ],
    ])('refuses %s in the browser without sending it', async (_case, file, message) => {
      serveStoredSources([]);
      server.use(
        http.get(`${API}/projects/${PROJECT_ID}`, () =>
          HttpResponse.json({
            ...PROJECT,
            id: PROJECT_ID,
            limits: { ...PROJECT.limits, source: { max_bytes: 512, max_words: 6000 } },
          }),
        ),
      );
      const received = recordUploads(() =>
        HttpResponse.json({ source_versions: [] }, { status: 201 }),
      );
      renderSources();
      const modal = await openAddSource();
      await modal.findByText(/Up to 512 bytes per file/);

      chooseFile(file);

      expect(await modal.findByRole('alert')).toHaveTextContent(message);
      expect(modal.getByLabelText('Upload a .txt or .md file')).toBeInvalid();

      submitUpload();

      expect(modal.getByRole('alert')).toHaveTextContent(message);
      expect(received).toHaveLength(0);
    });

    it('asks for a file before sending anything', async () => {
      serveStoredSources([]);
      const received = recordUploads(() =>
        HttpResponse.json({ source_versions: [] }, { status: 201 }),
      );
      renderSources();
      await openAddSource();

      submitUpload();

      expect(await screen.findByRole('alert')).toHaveTextContent('Choose a file to add.');
      expect(received).toHaveLength(0);
    });

    it.each([
      [
        'the word limit',
        413,
        'SOURCE_WORD_LIMIT_EXCEEDED',
        'Adding these files would bring the project to 6,400 words; the limit is 6,000.',
      ],
      ['an unreadable file', 422, 'SOURCE_UNREADABLE', 'brief.md is not UTF-8 text.'],
      ['the editor role', 403, 'FORBIDDEN', 'You need the editor role to add sources.'],
    ])('shows the server’s answer when it refuses %s', async (_case, status, code, message) => {
      serveStoredSources([]);
      recordUploads(() =>
        HttpResponse.json(errorBody(code, message, { details: { field: 'brief' } }), { status }),
      );
      renderSources();
      await openAddSource();

      chooseFile();
      submitUpload();

      expect(await screen.findByRole('alert')).toHaveTextContent(message);
      expect(screen.getByLabelText('Upload a .txt or .md file')).toHaveAccessibleDescription(
        message,
      );
      expect(addSourceDialog().getByRole('button', { name: 'Add source' })).toBeEnabled();
      await expectNoAccessibilityViolations();
    });

    it('retries a failed upload under the same idempotency key', async () => {
      serveStoredSources([]);
      const received = recordUploads(() =>
        received.length === 1
          ? HttpResponse.json(
              errorBody('INTERNAL_ERROR', 'An unexpected error occurred', { retryable: true }),
              { status: 500 },
            )
          : HttpResponse.json({ source_versions: [BRIEF] }, { status: 201 }),
      );
      renderSources();
      await openAddSource();
      chooseFile();
      submitUpload();
      expect(await screen.findByRole('alert')).toHaveTextContent('An unexpected error occurred');

      submitUpload();

      expect(await screen.findByText(/^SRC-1 brief.md added/)).toBeInTheDocument();
      expect(received).toHaveLength(2);
      expect(received[0]?.key).toBe(received[1]?.key);
    });

    it('shows that it is working, then reports an unreachable API without losing the file', async () => {
      serveStoredSources([]);
      server.use(
        http.post(SOURCES_URL, async () => {
          await delay(20);
          return HttpResponse.error();
        }),
      );
      renderSources();
      await openAddSource();

      chooseFile();
      submitUpload();

      expect(await screen.findByRole('button', { name: 'Adding…' })).toBeDisabled();
      expect(await screen.findByRole('alert')).toHaveTextContent('The server could not be reached');
      expect(addSourceDialog().getByRole('button', { name: 'Add source' })).toBeEnabled();
      expect(screen.getByRole('dialog', { name: 'Add a source' })).toBeInTheDocument();
    });

    it('opens from the “+” in the chat composer', async () => {
      serveStoredSources();

      renderApp(`/projects/${PROJECT_ID}/chat`);

      await userEvent.click(await screen.findByRole('button', { name: 'Add a source' }));

      expect(screen.getByRole('dialog', { name: 'Add a source' })).toBeInTheDocument();
      await expectNoAccessibilityViolations();
    });
  });

  describe('Remove source', () => {
    async function openViewerAndConfirm() {
      renderSources(`?version=${TRANSCRIPT.id}`);
      const viewer = within(await screen.findByRole('dialog', { name: 'SRC-2 transcript.txt' }));
      await userEvent.click(viewer.getByRole('button', { name: 'Remove source' }));
      expect(viewer.getByText(/Remove SRC-2 from the project\?/)).toBeInTheDocument();
      expect(viewer.getByRole('button', { name: 'Remove SRC-2' })).toHaveFocus();
      return viewer;
    }

    it('removes a source after confirmation and takes it off the list', async () => {
      serveStoredSources();
      const keys: (string | null)[] = [];
      server.use(
        http.delete(`${SOURCES_URL}/${TRANSCRIPT.source_id}`, ({ request }) => {
          keys.push(request.headers.get('Idempotency-Key'));
          serveStoredSources([BRIEF]);
          return HttpResponse.json({
            source_id: TRANSCRIPT.source_id,
            project_id: PROJECT_ID,
            kind: 'transcript',
            source_number: 2,
            removed_at: '2026-10-14T10:00:00Z',
            removed_by: '019a3a5e-0000-7000-8000-000000000002',
          });
        }),
      );
      const viewer = await openViewerAndConfirm();
      await expectNoAccessibilityViolations();

      await userEvent.click(viewer.getByRole('button', { name: 'Remove SRC-2' }));

      expect(await screen.findByText('SRC-2 removed.')).toBeInTheDocument();
      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
      expect(keys).toHaveLength(1);
      expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
      await waitFor(() => {
        expect(main().queryByRole('link', { name: 'transcript.txt' })).not.toBeInTheDocument();
      });
      expect(main().getByRole('link', { name: 'brief.md' })).toBeInTheDocument();
    });

    it('cancels without sending anything and returns focus to Remove source', async () => {
      serveStoredSources();
      let requests = 0;
      server.use(
        http.delete(`${SOURCES_URL}/${TRANSCRIPT.source_id}`, () => {
          requests += 1;
          return HttpResponse.json({});
        }),
      );
      const viewer = await openViewerAndConfirm();

      await userEvent.click(viewer.getByRole('button', { name: 'Cancel' }));

      expect(viewer.getByRole('button', { name: 'Remove source' })).toHaveFocus();
      expect(requests).toBe(0);
    });

    it('explains why a source that is used as evidence stays', async () => {
      serveStoredSources();
      server.use(
        http.delete(`${SOURCES_URL}/${TRANSCRIPT.source_id}`, () =>
          HttpResponse.json(
            errorBody('SOURCE_IN_USE', 'This source is used and cannot be removed.', {
              details: { used_by: { run: 1, backlog_version: 0, person: 2 } },
            }),
            { status: 409 },
          ),
        ),
      );
      const viewer = await openViewerAndConfirm();

      await userEvent.click(viewer.getByRole('button', { name: 'Remove SRC-2' }));

      expect(await viewer.findByRole('alert')).toHaveTextContent(
        'Used as evidence, so it can’t be removed: cited by 1 agent run and 2 people.',
      );
      expect(viewer.queryByRole('button', { name: /Remove/ })).not.toBeInTheDocument();
      expect(main().getByRole('link', { name: 'transcript.txt' })).toBeInTheDocument();
      await expectNoAccessibilityViolations();
    });

    it('shows any other refusal and lets the editor try again', async () => {
      serveStoredSources();
      let attempts = 0;
      server.use(
        http.delete(`${SOURCES_URL}/${TRANSCRIPT.source_id}`, () => {
          attempts += 1;
          return attempts === 1
            ? HttpResponse.json(
                errorBody('SOURCE_CHANGED', 'Someone else changed this source. Try again.'),
                { status: 409 },
              )
            : HttpResponse.json({
                source_id: TRANSCRIPT.source_id,
                project_id: PROJECT_ID,
                kind: 'transcript',
                source_number: 2,
                removed_at: '2026-10-14T10:00:00Z',
                removed_by: '019a3a5e-0000-7000-8000-000000000002',
              });
        }),
      );
      const viewer = await openViewerAndConfirm();
      await userEvent.click(viewer.getByRole('button', { name: 'Remove SRC-2' }));
      expect(await viewer.findByRole('alert')).toHaveTextContent(
        'Could not remove SRC-2. Someone else changed this source. Try again.',
      );

      await userEvent.click(viewer.getByRole('button', { name: 'Remove SRC-2' }));

      expect(await screen.findByText('SRC-2 removed.')).toBeInTheDocument();
      expect(attempts).toBe(2);
    });
  });

  it.each([
    ['viewer', VIEWER],
    ['approver without the editor role', APPROVER],
  ])('gives a %s a read-only page and viewer', async (_role, user) => {
    serveStoredSources();
    server.use(http.get(`${API}/me`, () => HttpResponse.json(user)));

    renderSources(`?version=${BRIEF.id}`);

    const viewer = within(await screen.findByRole('dialog', { name: 'SRC-1 brief.md' }));
    expect(await viewer.findByText('Students book study rooms.')).toBeInTheDocument();
    await screen.findByRole('button', { name: new RegExp(user.display_name) });
    expect(viewer.queryByRole('button', { name: 'Remove source' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add source' })).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('has no accessibility violations on the page or with Add a source open', async () => {
    serveStoredSources();
    renderSources();
    await main().findByRole('table', { name: 'Stored sources' });
    await expectNoAccessibilityViolations();

    await openAddSource();

    await expectNoAccessibilityViolations();
  });
});
