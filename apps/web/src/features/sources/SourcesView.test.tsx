import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { delay, http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { SourcesView } from '@/features/sources';
import { server } from '@/test/server';

import type { SourceBlock, SourceVersion } from './types';

const PROJECT_ID = '019a3a5e-0000-7000-8000-000000000001';
const SOURCES_URL = `*/api/v1/projects/${PROJECT_ID}/sources`;

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

function renderSourcesView(search = '') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/sources${search}`]}>
        <SourcesView projectId={PROJECT_ID} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
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
  // jsdom does not implement scrolling.
  scrollIntoView.mockReset();
  Element.prototype.scrollIntoView = scrollIntoView;
});

describe('SourcesView', () => {
  it('reloads stored sources with their identifiers and paragraphs', async () => {
    serveStoredSources();

    renderSourcesView();

    expect(screen.getByText('Loading sources…')).toBeInTheDocument();
    const stored = within(await screen.findByRole('navigation', { name: 'Stored sources' }));
    expect(stored.getByRole('link', { name: 'Project brief: brief.md' })).toBeInTheDocument();
    expect(
      stored.getByRole('link', { name: 'Meeting transcript: transcript.txt' }),
    ).toBeInTheDocument();
    expect(stored.getByText(BRIEF.source_id)).toBeInTheDocument();
    expect(stored.getByText(BRIEF.id)).toBeInTheDocument();
    expect(await screen.findByText('Students book study rooms.')).toBeInTheDocument();
    expect(screen.getByText('019a3a5e-0000-7000-8000-0000000000c1')).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Project brief: brief.md, version 1' }),
    ).toBeInTheDocument();
  });

  it('renders source text as text, never as markup', async () => {
    serveStoredSources();

    renderSourcesView();

    expect(
      await screen.findByText(
        'No recurring bookings <img src=x onerror="alert(1)"> in release one.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('invites an upload when the project has no sources', async () => {
    serveStoredSources([]);

    renderSourcesView();

    expect(await screen.findByText(/No sources yet/)).toBeInTheDocument();
  });

  it('shows another source when its link is followed', async () => {
    serveStoredSources();
    renderSourcesView();

    fireEvent.click(
      await screen.findByRole('link', { name: 'Meeting transcript: transcript.txt' }),
    );

    expect(await screen.findByText('Dana: keep it to single slots.')).toBeInTheDocument();
    expect(screen.queryByText('Students book study rooms.')).not.toBeInTheDocument();
  });

  it('moves to the paragraph a link selects', async () => {
    serveStoredSources();
    const selected = BRIEF_BLOCKS[1];

    renderSourcesView(`?version=${BRIEF.id}&block=${selected?.id ?? ''}`);

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

  it('says so when the stored sources cannot be loaded, and retries on request', async () => {
    server.use(
      http.get(SOURCES_URL, () =>
        HttpResponse.json(errorBody('NOT_FOUND', 'Project not found'), { status: 404 }),
      ),
    );
    renderSourcesView();
    expect(await screen.findByRole('alert')).toHaveTextContent('Project not found');
    serveStoredSources();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));

    expect(
      await screen.findByRole('link', { name: 'Project brief: brief.md' }),
    ).toBeInTheDocument();
  });

  it('uploads both files in one command and shows the stored paragraphs', async () => {
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
    renderSourcesView();
    await screen.findByText(/No sources yet/);

    chooseFiles();
    submitUpload();

    expect(await screen.findByRole('button', { name: 'Uploading…' })).toBeDisabled();
    expect(
      await screen.findByText('Stored brief.md (version 1) and transcript.txt (version 1).'),
    ).toBeInTheDocument();
    expect(received).toHaveLength(1);
    expect(received[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(received[0]?.brief).toBe('brief.md: Students book study rooms.');
    expect(received[0]?.transcript).toBe('transcript.txt: Dana: keep it to single slots.');
    expect(
      await screen.findByRole('link', { name: 'Project brief: brief.md' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Students book study rooms.')).toBeInTheDocument();
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
    renderSourcesView();

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
    renderSourcesView();

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
    renderSourcesView();
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
    renderSourcesView();

    chooseFiles();
    submitUpload();

    expect(await screen.findByRole('alert')).toHaveTextContent('The server could not be reached');
    expect(screen.getByRole('button', { name: 'Upload sources' })).toBeEnabled();
  });
});
