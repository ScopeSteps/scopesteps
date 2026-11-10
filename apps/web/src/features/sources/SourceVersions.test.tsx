import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { errorBody, PROJECT_ID, VIEWER } from '@/test/fixtures';
import { API, projectHandlers } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

import type { SourceBlock, SourceVersion } from './types';

const SOURCES_URL = `${API}/projects/${PROJECT_ID}/sources`;
const PAGE = `/projects/${PROJECT_ID}/sources`;
const SOURCE_ID = '019a3a5e-0000-7000-8000-0000000000a1';

const V1: SourceVersion = {
  id: '019a3a5e-0000-7000-8000-0000000000b1',
  source_id: SOURCE_ID,
  project_id: PROJECT_ID,
  kind: 'brief',
  source_number: 1,
  version: 1,
  filename: 'brief.md',
  media_type: 'text/markdown',
  checksum_sha256: 'a'.repeat(64),
  word_count: 4,
  block_count: 1,
  created_at: '2026-10-12T09:00:00Z',
};
const V2: SourceVersion = {
  ...V1,
  id: '019a3a5e-0000-7000-8000-0000000000b2',
  version: 2,
  filename: 'brief-final.md',
  checksum_sha256: 'b'.repeat(64),
  word_count: 6,
  created_at: '2026-10-14T09:00:00Z',
};

function blocks(version: SourceVersion, text: string): SourceBlock[] {
  return [
    {
      id: `${version.id.slice(0, -2)}c${String(version.version)}`,
      source_version_id: version.id,
      source_kind: 'brief',
      ordinal: 1,
      text,
      locator: { paragraph: 1, start_offset: 0, end_offset: text.length },
      page: null,
      start_ms: null,
      speaker: null,
    },
  ];
}

interface Received {
  key: string | null;
  filename: string | null;
}

/**
 * The brief held as the server holds it: v1 only, until a different file is uploaded. The same
 * file as the current version returns that version.
 */
function serveBrief({ versions = [V1] }: { versions?: SourceVersion[] } = {}) {
  let held = [...versions];
  const received: Received[] = [];
  server.use(
    http.get(SOURCES_URL, () => HttpResponse.json({ source_versions: held.slice(0, 1) })),
    http.get(`${SOURCES_URL}/${SOURCE_ID}/versions`, () =>
      HttpResponse.json({ source_versions: held }),
    ),
    http.get(`${SOURCES_URL}/${V1.id}/blocks`, () =>
      HttpResponse.json(blocks(V1, 'Students book rooms.')),
    ),
    http.get(`${SOURCES_URL}/${V2.id}/blocks`, () =>
      HttpResponse.json(blocks(V2, 'Students and staff book rooms.')),
    ),
    http.post(`${SOURCES_URL}/${SOURCE_ID}/versions`, async ({ request }) => {
      const file = (await request.formData()).get('file');
      const filename = file instanceof File ? file.name : null;
      received.push({ key: request.headers.get('Idempotency-Key'), filename });
      const current = held[0] ?? V1;
      if (filename === current.filename) {
        return HttpResponse.json(current, { status: 201 });
      }
      held = [V2, ...held];
      return HttpResponse.json(V2, { status: 201 });
    }),
  );
  return received;
}

function choose(name: string, text = 'Students and staff book rooms.') {
  fireEvent.change(screen.getByLabelText('File for the new version of SRC-1'), {
    target: { files: [new File([text], name)] },
  });
}

async function openViewer(search = `?version=${V1.id}`) {
  renderApp(`${PAGE}${search}`);
  return within(await screen.findByRole('dialog', { name: /^SRC-1/ }));
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

describe('Uploading a new version of a source', () => {
  it('stores the file as the next version, says so and opens it, keeping v1 in the list', async () => {
    const received = serveBrief();
    const viewer = await openViewer();
    await viewer.findByText('Students book rooms.');

    choose('brief-final.md');

    await waitFor(() => {
      expect(received).toHaveLength(1);
    });
    expect(received[0]).toEqual({ key: expect.any(String) as string, filename: 'brief-final.md' });
    expect(await screen.findByText('Saved as v2 of SRC-1.')).toBeInTheDocument();
    const updated = within(await screen.findByRole('dialog', { name: 'SRC-1 brief-final.md' }));
    expect(await updated.findByText('Students and staff book rooms.')).toBeInTheDocument();
    expect(updated.getByText(/^Project brief · v2 ·/)).toBeInTheDocument();
    const list = within(updated.getByRole('region', { name: 'Versions' }));
    expect(list.getByRole('button', { name: 'Open v2: brief-final.md' })).toHaveAttribute(
      'aria-current',
      'true',
    );
    expect(list.getByText('Current')).toBeInTheDocument();
    expect(list.getByRole('button', { name: 'Open v1: brief.md' })).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('says nothing changed when the file is the same as the current version', async () => {
    const received = serveBrief();
    const viewer = await openViewer();

    choose('brief.md', 'Students book rooms.');

    expect(await viewer.findByRole('status')).toHaveTextContent(
      'That file is the same as v1, so nothing changed.',
    );
    expect(received).toHaveLength(1);
    expect(viewer.queryByRole('region', { name: 'Versions' })).not.toBeInTheDocument();
  });

  it('shows the server’s refusal in plain words', async () => {
    serveBrief();
    server.use(
      http.post(`${SOURCES_URL}/${SOURCE_ID}/versions`, () =>
        HttpResponse.json(
          errorBody(
            'SOURCE_SCANNED',
            'brief.pdf has scanned pages with no text. Upload a copy with text.',
          ),
          { status: 422 },
        ),
      ),
    );
    const viewer = await openViewer();

    choose('brief.pdf');

    expect(await viewer.findByRole('alert')).toHaveTextContent(
      'The new version was not saved. brief.pdf has scanned pages with no text. Upload a copy with text.',
    );
  });

  it('refuses a file type the API does not take, without sending it', async () => {
    const received = serveBrief();
    const viewer = await openViewer();

    choose('brief.xlsx');

    expect(await viewer.findByRole('alert')).toHaveTextContent(
      'The new version was not saved. brief.xlsx is not a .txt, .md, .docx, .pdf or .vtt file.',
    );
    expect(received).toHaveLength(0);
  });

  it('is not offered to a viewer', async () => {
    serveBrief();
    server.use(http.get(`${API}/me`, () => HttpResponse.json(VIEWER)));
    const viewer = await openViewer();

    await viewer.findByText('Students book rooms.');
    await screen.findByRole('button', { name: new RegExp(VIEWER.display_name) });
    expect(viewer.queryByRole('button', { name: 'Upload new version' })).not.toBeInTheDocument();
  });
});

describe('Earlier versions of a source', () => {
  it('opens v1 read-only, says so and leads back to the current version', async () => {
    serveBrief({ versions: [V2, V1] });
    const viewer = await openViewer(`?version=${V1.id}&source=${SOURCE_ID}`);

    expect(await viewer.findByText('Students book rooms.')).toBeInTheDocument();
    expect(
      viewer.getByText(/This is v1, an earlier version\. It is kept as it was/),
    ).toBeInTheDocument();
    expect(viewer.queryByRole('button', { name: 'Upload new version' })).not.toBeInTheDocument();
    expect(viewer.queryByRole('button', { name: 'Remove source' })).not.toBeInTheDocument();
    await expectNoAccessibilityViolations();

    await userEvent.click(viewer.getByRole('button', { name: 'Open the current version, v2' }));

    const current = within(await screen.findByRole('dialog', { name: 'SRC-1 brief-final.md' }));
    expect(await current.findByText('Students and staff book rooms.')).toBeInTheDocument();
    expect(current.getByRole('button', { name: 'Upload new version' })).toBeInTheDocument();
  });
});
