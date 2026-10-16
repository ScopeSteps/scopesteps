import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/apiError';

import type { Person } from './people';
import { answersFrom, confirmedCount, personPick, refusedField } from './speakers';
import type { SpeakerDraft, TranscriptSpeakers } from './speakers';

const DANA: Person = {
  id: 'dana',
  project_id: 'p',
  revision: 1,
  origin: 'extracted',
  name: 'Dana Ruiz',
  role: '',
  entered_name: null,
  meeting_role: { value: 'Sponsor', set_by: 'u', set_at: '2026-10-16T09:00:00Z' },
  spoke_in: [],
  extracted: null,
  correction: null,
  confirmed_rights: null,
  created_at: '2026-10-16T09:00:00Z',
};
const PEOPLE = [DANA];

function draft(
  key: string,
  pick: SpeakerDraft['pick'],
  meetingRole = '',
  name = key,
): SpeakerDraft {
  return { key, pick, meetingRole, name };
}

describe('answersFrom', () => {
  it('sends each answered speaker, leaves unanswered ones out and tracks whose answer is whose', () => {
    const { answers, keys } = answersFrom(
      [
        draft('mira', 'new', '  Workshop lead ', 'Mira Holt'),
        draft('tomas', ''),
        draft('dana', personPick('dana'), 'Sponsor'),
        draft('speaker 3', 'not_a_person'),
      ],
      PEOPLE,
    );

    expect(answers).toEqual([
      { label_key: 'mira', choice: 'new', name: 'Mira Holt', meeting_role: 'Workshop lead' },
      { label_key: 'dana', choice: 'link', person_id: 'dana', meeting_role: null },
      { label_key: 'speaker 3', choice: 'not_a_person' },
    ]);
    expect(keys).toEqual(['mira', 'dana', 'speaker 3']);
  });

  it('sends a linked participant’s meeting role only when it changed, blank to clear it', () => {
    const changed = answersFrom([draft('dana', personPick('dana'), 'Developer')], PEOPLE);
    const cleared = answersFrom([draft('dana', personPick('dana'), ' ')], PEOPLE);

    expect(changed.answers[0]).toMatchObject({ meeting_role: 'Developer' });
    expect(cleared.answers[0]).toMatchObject({ meeting_role: '' });
  });
});

describe('refusedField', () => {
  function refusal(field: unknown, status = 422) {
    return new ApiError(status, {
      code: 'INVALID_INPUT',
      message: 'Too long.',
      request_id: 'r',
      retryable: false,
      details: { field },
    });
  }

  it.each([
    ['speakers[1].name', 'tomas', 'name'],
    ['speakers[0].meeting_role', 'mira', 'meeting_role'],
    ['speakers[1].person_id', 'tomas', 'pick'],
    ['speakers[0].label_key', 'mira', 'pick'],
  ] as const)('puts %s next to the speaker it was sent for', (field, key, shown) => {
    expect(refusedField(refusal(field), ['mira', 'tomas'])).toEqual({
      key,
      field: shown,
      message: 'Too long.',
    });
  });

  it('ignores refusals it cannot place', () => {
    expect(refusedField(refusal('speakers[5].name'), ['mira'])).toBeNull();
    expect(refusedField(refusal('expected_revision'), ['mira'])).toBeNull();
    expect(refusedField(refusal('speakers[0].name', 409), ['mira'])).toBeNull();
    expect(refusedField(new Error('offline'), ['mira'])).toBeNull();
  });
});

describe('confirmedCount', () => {
  it('counts every speaker someone answered for or that linked itself', () => {
    const statuses = ['linked', 'linked_automatically', 'not_a_person', 'unconfirmed'] as const;
    const transcript: TranscriptSpeakers = {
      source_id: 's',
      source_version_id: 'v',
      revision: 1,
      speakers: statuses.map((status) => ({
        key: status,
        label: status,
        turn_count: 1,
        first_block_id: 'b',
        first_paragraph: 1,
        sample: '',
        status,
        person_id: null,
        assigned_by: null,
        assigned_at: null,
      })),
    };

    expect(confirmedCount(transcript)).toBe(3);
  });
});
