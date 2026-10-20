import type { components } from '@scopesteps/api-client';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { BRIEF, PROJECT, PROJECT_ID, REVIEWER_ID, TRANSCRIPT, VIEWER } from '@/test/fixtures';
import { API, PEOPLE_URL, projectHandlers, SOURCES_URL, SPEAKERS_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';
import { resetViewport, setNarrowViewport } from '@/test/viewport';

type Transcript = components['schemas']['TranscriptSpeakersResponse'];
type Speaker = components['schemas']['SpeakerResponse'];
type Person = components['schemas']['PersonResponse'];

const PAGE = `/projects/${PROJECT_ID}/sources`;
const PUT_URL = `${API}/projects/${PROJECT_ID}/sources/:sourceId/speakers`;
const DIALOG = `Who's who in SRC-2 transcript.md`;
const DANA_ID = '019a3a5e-0000-7000-8000-000000000201';

function speaker(label: string, overrides: Partial<Speaker> = {}): Speaker {
  return {
    key: label.toLowerCase(),
    label,
    turn_count: 2,
    first_block_id: '019a3a5e-0000-7000-8000-0000000000c3',
    first_paragraph: 1,
    sample: `${label} opens the meeting.`,
    status: 'unconfirmed',
    person_id: null,
    assigned_by: null,
    assigned_at: null,
    ...overrides,
  };
}

const UNANSWERED: Transcript = {
  source_id: TRANSCRIPT.source_id,
  source_version_id: TRANSCRIPT.id,
  revision: 0,
  speakers: [
    speaker('Mira Holt'),
    speaker('Dana', { status: 'linked_automatically', person_id: DANA_ID }),
    speaker('Speaker 3', { turn_count: 1 }),
  ],
};

const DANA: Person = {
  id: DANA_ID,
  project_id: PROJECT_ID,
  revision: 1,
  origin: 'extracted',
  name: 'Dana Ruiz',
  role: 'Facilities Manager',
  entered_name: null,
  meeting_role: {
    value: 'Sponsor',
    set_by: REVIEWER_ID,
    set_at: '2026-10-16T09:00:00Z',
  },
  spoke_in: [],
  extracted: null,
  correction: null,
  confirmed_rights: null,
  created_at: '2026-10-16T09:00:00Z',
};

function serve(transcript: Transcript = UNANSWERED, people: Person[] = [DANA]) {
  server.use(
    http.get(SPEAKERS_URL, () => HttpResponse.json({ transcripts: [transcript] })),
    http.get(PEOPLE_URL, () => HttpResponse.json({ people, unconfirmed_speakers: [] })),
  );
}

interface Sent {
  key: string | null;
  body: unknown;
}

function recordSaves(respond: (body: unknown) => Response): Sent[] {
  const sent: Sent[] = [];
  server.use(
    http.put(PUT_URL, async ({ request }) => {
      const body = await request.json();
      sent.push({ key: request.headers.get('Idempotency-Key'), body });
      return respond(body);
    }),
  );
  return sent;
}

function main() {
  return within(screen.getByRole('main'));
}

function dialog() {
  return within(screen.getByRole('dialog', { name: DIALOG }));
}

function row(label: string) {
  return within(dialog().getByRole('listitem', { name: label }));
}

async function openFromSources() {
  renderApp(PAGE);
  await userEvent.click(
    await main().findByRole('button', { name: /^Who's who in SRC-2 transcript\.md/ }),
  );
  return dialog();
}

function errorBody(code: string, message: string, details: object = {}) {
  return {
    code,
    message,
    request_id: '019a3a5e-1111-7000-8000-000000000000',
    retryable: false,
    details,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  server.use(...projectHandlers());
});

afterEach(() => {
  resetViewport();
});

describe("Who's who", () => {
  it('lists each speaker with their turns, first line and status, nothing chosen for them', async () => {
    serve();
    const modal = await openFromSources();

    expect(modal.getByRole('heading', { level: 2, name: DIALOG })).toHaveFocus();
    expect(modal.getAllByRole('listitem')).toHaveLength(3);
    expect(row('Mira Holt').getByText('2 turns')).toBeInTheDocument();
    expect(row('Speaker 3').getByText('1 turn')).toBeInTheDocument();
    expect(row('Mira Holt').getByText(/Mira Holt opens the meeting\./)).toBeInTheDocument();
    expect(row('Mira Holt').getByText('Unconfirmed')).toBeInTheDocument();
    expect(row('Mira Holt').getByRole('combobox', { name: 'Who is Mira Holt?' })).toHaveValue('');
    expect(
      row('Mira Holt').queryByRole('combobox', { name: 'Meeting role of Mira Holt' }),
    ).not.toBeInTheDocument();
  });

  it('shows an automatically linked speaker as linked, with their meeting role, and lets it change', async () => {
    serve();
    await openFromSources();

    const dana = row('Dana');
    expect(dana.getByText('Linked automatically')).toBeInTheDocument();
    expect(dana.getByRole('combobox', { name: 'Who is Dana?' })).toHaveDisplayValue('Dana Ruiz');
    expect(dana.getByRole('combobox', { name: 'Meeting role of Dana' })).toHaveValue('Sponsor');

    await userEvent.selectOptions(
      dana.getByRole('combobox', { name: 'Who is Dana?' }),
      'Not a person',
    );
    expect(dana.queryByRole('combobox', { name: 'Meeting role of Dana' })).not.toBeInTheDocument();
  });

  it('saves every answer in one request and closes', async () => {
    serve();
    const saved: Transcript = {
      ...UNANSWERED,
      revision: 1,
      speakers: [
        speaker('Mira Holt', {
          status: 'linked',
          person_id: '019a3a5e-0000-7000-8000-000000000299',
        }),
        speaker('Dana', { status: 'linked', person_id: DANA_ID }),
        speaker('Speaker 3', { turn_count: 1, status: 'not_a_person' }),
      ],
    };
    const sent = recordSaves(() => {
      serve(saved);
      return HttpResponse.json(saved);
    });
    await openFromSources();

    await userEvent.selectOptions(
      row('Mira Holt').getByRole('combobox', { name: 'Who is Mira Holt?' }),
      'New participant…',
    );
    const name = row('Mira Holt').getByRole('textbox', {
      name: 'Name of the new participant for Mira Holt',
    });
    expect(name).toHaveValue('Mira Holt');
    await userEvent.type(
      row('Mira Holt').getByRole('combobox', { name: 'Meeting role of Mira Holt' }),
      'Workshop lead',
    );
    await userEvent.selectOptions(
      row('Speaker 3').getByRole('combobox', { name: 'Who is Speaker 3?' }),
      'Not a person',
    );
    await userEvent.click(dialog().getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(sent).toHaveLength(1);
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[0]?.body).toEqual({
      expected_revision: 0,
      speakers: [
        { label_key: 'mira holt', choice: 'new', name: 'Mira Holt', meeting_role: 'Workshop lead' },
        { label_key: 'dana', choice: 'link', person_id: DANA_ID, meeting_role: null },
        { label_key: 'speaker 3', choice: 'not_a_person' },
      ],
    });
  });

  it('reloads the latest answers on a 409 and says why nothing was saved', async () => {
    serve();
    const theirs: Transcript = {
      ...UNANSWERED,
      revision: 2,
      speakers: UNANSWERED.speakers.map((each) =>
        each.key === 'speaker 3' ? { ...each, status: 'not_a_person' } : each,
      ),
    };
    const sent = recordSaves(() => {
      serve(theirs);
      return HttpResponse.json(
        errorBody('SPEAKERS_CHANGED', 'Someone changed it.', { current_revision: 2 }),
        { status: 409 },
      );
    });
    await openFromSources();

    await userEvent.selectOptions(
      row('Mira Holt').getByRole('combobox', { name: 'Who is Mira Holt?' }),
      'Not a person',
    );
    await userEvent.click(dialog().getByRole('button', { name: 'Save' }));

    expect(await dialog().findByRole('alert')).toHaveTextContent(
      "Someone else changed who's who in this transcript, so your answers were not saved.",
    );
    await waitFor(() => {
      expect(row('Speaker 3').getByRole('combobox', { name: 'Who is Speaker 3?' })).toHaveValue(
        'not_a_person',
      );
    });
    expect(row('Mira Holt').getByRole('combobox', { name: 'Who is Mira Holt?' })).toHaveValue('');
    expect(sent).toHaveLength(1);
  });

  it('shows a refused field next to the speaker it belongs to', async () => {
    serve();
    recordSaves(() =>
      HttpResponse.json(
        errorBody('PARTICIPANT_EXISTS', 'A participant with this name is already on the project.', {
          field: 'speakers[0].name',
          person_id: DANA_ID,
        }),
        { status: 422 },
      ),
    );
    await openFromSources();
    await userEvent.selectOptions(
      row('Mira Holt').getByRole('combobox', { name: 'Who is Mira Holt?' }),
      'New participant…',
    );

    await userEvent.click(dialog().getByRole('button', { name: 'Save' }));

    const name = await row('Mira Holt').findByRole('textbox', {
      name: 'Name of the new participant for Mira Holt',
    });
    await waitFor(() => {
      expect(name).toHaveAccessibleDescription(
        'A participant with this name is already on the project.',
      );
    });
    expect(name).toHaveAttribute('aria-invalid', 'true');
    expect(dialog().queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the answers read-only to a member without the Editor role', async () => {
    serve();
    server.use(
      http.get(`${API}/me`, () => HttpResponse.json(VIEWER)),
      http.get(`${API}/projects/${PROJECT_ID}`, () =>
        HttpResponse.json({ ...PROJECT, roles: ['viewer'] }),
      ),
    );
    const modal = await openFromSources();

    expect(modal.queryByRole('combobox')).not.toBeInTheDocument();
    expect(modal.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(row('Dana').getByText('Dana Ruiz')).toBeInTheDocument();
    expect(row('Dana').getByText('Sponsor')).toBeInTheDocument();
    expect(row('Mira Holt').getByText('Not confirmed yet')).toBeInTheDocument();
    await userEvent.click(modal.getByRole('button', { name: 'Done' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('is used from the keyboard: Escape cancels it and focus returns to the row', async () => {
    serve();
    const sent = recordSaves(() => HttpResponse.json(UNANSWERED));
    await openFromSources();

    await userEvent.tab();
    await userEvent.tab();
    expect(row('Mira Holt').getByRole('combobox', { name: 'Who is Mira Holt?' })).toHaveFocus();
    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(
      main().getByRole('button', { name: /^Who's who in SRC-2 transcript\.md/ }),
    ).toHaveFocus();
    expect(sent).toHaveLength(0);
  });

  it('opens after uploading a transcript with speakers, and cancelling leaves them unconfirmed', async () => {
    const added = {
      ...TRANSCRIPT,
      id: '019a3a5e-0000-7000-8000-0000000000b9',
      source_id: '019a3a5e-0000-7000-8000-0000000000a9',
      source_number: 3,
      filename: 'kickoff.txt',
    };
    server.use(
      http.post(SOURCES_URL, () => {
        server.use(
          http.get(SOURCES_URL, () =>
            HttpResponse.json({ source_versions: [BRIEF, TRANSCRIPT, added] }),
          ),
          http.get(SPEAKERS_URL, () =>
            HttpResponse.json({
              transcripts: [
                { ...UNANSWERED, source_id: added.source_id, source_version_id: added.id },
              ],
            }),
          ),
        );
        return HttpResponse.json({ source_versions: [added] }, { status: 201 });
      }),
    );
    const sent = recordSaves(() => HttpResponse.json(UNANSWERED));
    renderApp(PAGE);
    await userEvent.click(await main().findByRole('button', { name: 'Add source' }));
    fireEvent.change(screen.getByLabelText('Upload .txt or .md files'), {
      target: { files: [new File(['Mira Holt: hello.'], 'kickoff.txt')] },
    });
    await userEvent.selectOptions(screen.getByLabelText('Type of kickoff.txt'), 'transcript');
    await userEvent.click(
      within(screen.getByRole('dialog', { name: 'Add a source' })).getByRole('button', {
        name: 'Add source',
      }),
    );

    const modal = within(
      await screen.findByRole('dialog', { name: "Who's who in SRC-3 kickoff.txt" }),
    );
    expect(modal.getAllByRole('listitem')).toHaveLength(3);
    await userEvent.click(modal.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(sent).toHaveLength(0);
  });

  it('opens nothing after uploading a transcript without speaker labels', async () => {
    server.use(
      http.post(SOURCES_URL, () =>
        HttpResponse.json(
          { source_versions: [{ ...TRANSCRIPT, id: 'new', source_id: 'new' }] },
          { status: 201 },
        ),
      ),
    );
    renderApp(PAGE);
    await userEvent.click(await main().findByRole('button', { name: 'Add source' }));
    fireEvent.change(screen.getByLabelText('Upload .txt or .md files'), {
      target: { files: [new File(['Notes without labels.'], 'notes.txt')] },
    });
    await userEvent.selectOptions(screen.getByLabelText('Type of notes.txt'), 'transcript');
    await userEvent.click(
      within(screen.getByRole('dialog', { name: 'Add a source' })).getByRole('button', {
        name: 'Add source',
      }),
    );

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(main().queryByRole('button', { name: /Who's who/ })).not.toBeInTheDocument();
  });

  it('has no accessibility violations, wide or below 900px', async () => {
    serve();
    await openFromSources();
    await userEvent.selectOptions(
      row('Mira Holt').getByRole('combobox', { name: 'Who is Mira Holt?' }),
      'New participant…',
    );
    await expectNoAccessibilityViolations();

    setNarrowViewport(true);
    await expectNoAccessibilityViolations();
  });
});
