import type { components } from '@scopesteps/api-client';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import { expectNoAccessibilityViolations } from '@/test/axe';
import { PROJECT_ID, REVIEWER_ID, TRANSCRIPT } from '@/test/fixtures';
import { API, PEOPLE_URL, projectHandlers, SPEAKERS_URL } from '@/test/handlers';
import { renderApp } from '@/test/renderApp';
import { server } from '@/test/server';

type Person = components['schemas']['PersonResponse'];
type Transcript = components['schemas']['TranscriptSpeakersResponse'];
type Speaker = components['schemas']['SpeakerResponse'];
type UnconfirmedSpeaker = components['schemas']['UnconfirmedSpeakerResponse'];

const PEOPLE_PAGE = `/projects/${PROJECT_ID}/people`;
const SOURCES_PAGE = `/projects/${PROJECT_ID}/sources`;
const MIRA_ID = '019a3a5e-0000-7000-8000-000000000211';
const SET_AT = '2026-10-16T09:00:00Z';

function person(id: string, overrides: Partial<Person>): Person {
  return {
    id,
    project_id: PROJECT_ID,
    revision: 1,
    origin: 'extracted',
    name: 'Someone',
    role: '',
    entered_name: null,
    meeting_role: null,
    spoke_in: [],
    extracted: null,
    correction: null,
    confirmed_rights: null,
    created_at: SET_AT,
    ...overrides,
  };
}

const EXTRACTED = {
  role: 'Facilities Manager',
  said: '',
  stated_rights: 'not_stated' as const,
  evidence: [],
  rights_evidence: [],
  run_id: '019a3a5e-0000-7000-8000-0000000000f1',
  extracted_at: SET_AT,
};
const MIRA = person(MIRA_ID, {
  origin: 'confirmed_speaker',
  name: 'Mira Holt',
  entered_name: 'Mira Holt',
  meeting_role: { value: 'Sponsor', set_by: REVIEWER_ID, set_at: SET_AT },
  spoke_in: [{ source_id: TRANSCRIPT.source_id, label: 'Mira', status: 'linked' }],
});
const DANA = person('019a3a5e-0000-7000-8000-000000000212', {
  name: 'Dana Ruiz',
  role: 'Facilities Manager',
  extracted: { name: 'Dana Ruiz', ...EXTRACTED },
});
const SAM = person('019a3a5e-0000-7000-8000-000000000213', {
  name: 'Sam Okafor',
  meeting_role: { value: 'End-user representative', set_by: REVIEWER_ID, set_at: SET_AT },
  spoke_in: [{ source_id: TRANSCRIPT.source_id, label: 'Sam', status: 'linked_automatically' }],
  extracted: { name: 'Sam Okafor', ...EXTRACTED, role: 'Student' },
});

function speaker(label: string, overrides: Partial<Speaker> = {}): Speaker {
  return {
    key: label.toLowerCase(),
    label,
    turn_count: 1,
    first_block_id: '019a3a5e-0000-7000-8000-0000000000c3',
    first_paragraph: 1,
    sample: `${label} speaks.`,
    status: 'unconfirmed',
    person_id: null,
    assigned_by: null,
    assigned_at: null,
    ...overrides,
  };
}

const KICKOFF: Transcript = {
  source_id: TRANSCRIPT.source_id,
  source_version_id: TRANSCRIPT.id,
  revision: 1,
  speakers: [
    speaker('Mira', { status: 'linked', person_id: MIRA_ID }),
    speaker('Tomas'),
    speaker('Guest 1'),
  ],
};
const UNCONFIRMED: UnconfirmedSpeaker[] = [
  { source_id: TRANSCRIPT.source_id, key: 'tomas', label: 'Tomas' },
  { source_id: TRANSCRIPT.source_id, key: 'guest 1', label: 'Guest 1' },
];

function serve(unconfirmed: UnconfirmedSpeaker[] = UNCONFIRMED, transcript = KICKOFF) {
  server.use(
    http.get(PEOPLE_URL, () =>
      HttpResponse.json({ people: [MIRA, DANA, SAM], unconfirmed_speakers: unconfirmed }),
    ),
    http.get(SPEAKERS_URL, () => HttpResponse.json({ transcripts: [transcript] })),
  );
}

function main() {
  return within(screen.getByRole('main'));
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  server.use(...projectHandlers());
});

describe('People and Sources with transcript speakers', () => {
  it('counts unconfirmed speakers on the People badge, in words as well as colour', async () => {
    serve();
    renderApp(PEOPLE_PAGE);

    const link = await screen.findByRole('link', { name: 'People 2 speakers to confirm' });
    expect(within(link).getByTitle('2 speakers to confirm')).toHaveTextContent('2');
  });

  it('drops the badge once every speaker is confirmed or marked not a person', async () => {
    serve();
    server.use(
      http.put(`${API}/projects/${PROJECT_ID}/sources/:sourceId/speakers`, () => {
        const done: Transcript = {
          ...KICKOFF,
          revision: 2,
          speakers: KICKOFF.speakers.map((each) =>
            each.status === 'unconfirmed' ? { ...each, status: 'not_a_person' } : each,
          ),
        };
        serve([], done);
        return HttpResponse.json(done);
      }),
    );
    renderApp(PEOPLE_PAGE);
    await screen.findByRole('link', { name: 'People 2 speakers to confirm' });

    await userEvent.click(
      await main().findByRole('button', { name: "Who's who in SRC-2 transcript.md" }),
    );
    const modal = within(
      await screen.findByRole('dialog', { name: "Who's who in SRC-2 transcript.md" }),
    );
    for (const label of ['Tomas', 'Guest 1']) {
      await userEvent.selectOptions(
        modal.getByRole('combobox', { name: `Who is ${label}?` }),
        'Not a person',
      );
    }
    await userEvent.click(modal.getByRole('button', { name: 'Save' }));

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /^People/ })).toHaveAccessibleName('People');
    });
    expect(main().queryByRole('region', { name: /speakers? to confirm/ })).not.toBeInTheDocument();
  });

  it('lists the speakers to confirm by transcript', async () => {
    serve();
    renderApp(PEOPLE_PAGE);

    const section = within(await main().findByRole('region', { name: '2 speakers to confirm' }));
    const transcripts = within(
      section.getByRole('list', { name: 'Transcripts with speakers to confirm' }),
    );
    expect(transcripts.getByRole('listitem')).toHaveTextContent(
      "SRC-2 transcript.md: Tomas, Guest 1Who's who",
    );
    expect(section.getByText(/the agent treats them as role unknown/)).toBeInTheDocument();
    await expectNoAccessibilityViolations();
  });

  it('says where each person comes from and shows their meeting role', async () => {
    serve();
    renderApp(PEOPLE_PAGE);

    const mira = within(await screen.findByRole('article', { name: 'Mira Holt' }));
    const dana = within(screen.getByRole('article', { name: 'Dana Ruiz' }));
    const sam = within(screen.getByRole('article', { name: 'Sam Okafor' }));

    const origins = (card: typeof mira, name: string) =>
      within(card.getByRole('list', { name: `Where ${name} comes from` }))
        .getAllByRole('listitem')
        .map((item) => item.textContent);
    expect(origins(mira, 'Mira Holt')).toEqual(['Spoke in a transcript']);
    expect(origins(dana, 'Dana Ruiz')).toEqual(['Named in a source']);
    expect(origins(sam, 'Sam Okafor')).toEqual(['Spoke in a transcript', 'Named in a source']);
    expect(mira.getByText('Meeting role:').parentElement).toHaveTextContent(
      'Meeting role: Sponsor',
    );
    expect(dana.queryByText('Meeting role:')).not.toBeInTheDocument();
  });

  it('shows how many of a transcript’s speakers are confirmed in Sources, and opens Who’s who', async () => {
    serve();
    renderApp(SOURCES_PAGE);

    const summary = await main().findByRole('button', {
      name: "Who's who in SRC-2 transcript.md: 1 of 3 speakers confirmed",
    });
    expect(summary).toHaveTextContent('1 of 3 speakers confirmed');

    await userEvent.click(summary);

    expect(
      await screen.findByRole('dialog', { name: "Who's who in SRC-2 transcript.md" }),
    ).toBeInTheDocument();
  });

  it('keeps every count server-side: nothing about speakers goes in browser storage', async () => {
    serve();
    renderApp(SOURCES_PAGE);
    await main().findByRole('button', { name: /1 of 3 speakers confirmed/ });

    const stored = [window.localStorage, window.sessionStorage].flatMap((storage) =>
      Object.keys(storage).map((key) => `${key}=${storage.getItem(key) ?? ''}`),
    );
    expect(stored.filter((entry) => /speaker|tomas|mira/i.test(entry))).toEqual([]);
  });
});
