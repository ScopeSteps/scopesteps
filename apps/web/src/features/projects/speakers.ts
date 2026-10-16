import type { components } from '@scopesteps/api-client';

import type { TagTone } from '@/components/Tag';
import { ApiError } from '@/lib/apiError';

import type { Person } from './people';

export type TranscriptSpeakers = components['schemas']['TranscriptSpeakersResponse'];
export type Speaker = components['schemas']['SpeakerResponse'];
export type SpeakerStatus = Speaker['status'];
export type SpeakerAnswer = components['schemas']['SpeakerMappingRequest']['speakers'][number];

/** Offered in the meeting role field; any other text is allowed too. */
export const MEETING_ROLE_SUGGESTIONS = [
  'Sponsor',
  'Product owner',
  'Business analyst',
  'Developer',
  'Designer',
  'QA',
  'Subject-matter expert',
  'End-user representative',
] as const;

export function speakersQueryKey(projectId: string) {
  return ['projects', projectId, 'speakers'] as const;
}

export const STATUS_TAGS: Record<SpeakerStatus, { label: string; tone: TagTone }> = {
  linked: { label: 'Linked', tone: 'ok' },
  linked_automatically: { label: 'Linked automatically', tone: 'accent' },
  not_a_person: { label: 'Not a person', tone: 'neutral' },
  unconfirmed: { label: 'Unconfirmed', tone: 'warn' },
};

/** What the participant picker holds: nobody yet, a person, a new participant or not a person. */
export type Pick = '' | 'new' | 'not_a_person' | `person:${string}`;

/** One speaker's answer as the editor is filling it in. */
export interface SpeakerDraft {
  key: string;
  pick: Pick;
  /** The new participant's name; starts as the label the transcript gives. */
  name: string;
  meetingRole: string;
}

export function personPick(personId: string): Pick {
  return `person:${personId}`;
}

function pickedPerson(pick: Pick): string | null {
  return pick.startsWith('person:') ? pick.slice('person:'.length) : null;
}

function meetingRoleOf(people: readonly Person[], personId: string | null): string {
  return people.find((person) => person.id === personId)?.meeting_role?.value ?? '';
}

/** The form as the server holds the transcript: answered and automatic links filled in. */
export function draftsFrom(
  transcript: TranscriptSpeakers,
  people: readonly Person[],
): SpeakerDraft[] {
  return transcript.speakers.map((speaker) => {
    const pick: Pick =
      speaker.status === 'not_a_person'
        ? 'not_a_person'
        : speaker.person_id
          ? personPick(speaker.person_id)
          : '';
    return {
      key: speaker.key,
      pick,
      name: speaker.label,
      meetingRole: meetingRoleOf(people, speaker.person_id),
    };
  });
}

/**
 * The whole answer to send, and which speaker each entry belongs to, so a field the server
 * refuses can be shown next to that speaker. A speaker with no pick is left out and stays
 * unconfirmed. A linked participant's meeting role is sent only when it was changed.
 */
export function answersFrom(
  drafts: readonly SpeakerDraft[],
  people: readonly Person[],
): { answers: SpeakerAnswer[]; keys: string[] } {
  const answers: SpeakerAnswer[] = [];
  const keys: string[] = [];
  for (const draft of drafts) {
    const meetingRole = draft.meetingRole.trim();
    const personId = pickedPerson(draft.pick);
    if (draft.pick === 'new') {
      answers.push({
        label_key: draft.key,
        choice: 'new',
        name: draft.name,
        meeting_role: meetingRole || null,
      });
    } else if (draft.pick === 'not_a_person') {
      answers.push({ label_key: draft.key, choice: 'not_a_person' });
    } else if (personId !== null) {
      const unchanged = meetingRole === meetingRoleOf(people, personId);
      answers.push({
        label_key: draft.key,
        choice: 'link',
        person_id: personId,
        meeting_role: unchanged ? null : meetingRole,
      });
    } else {
      continue;
    }
    keys.push(draft.key);
  }
  return { answers, keys };
}

export type SpeakerField = 'name' | 'meeting_role' | 'pick';

/** The speaker and field a 422 names (`details.field` is `speakers[2].name`), if any. */
export function refusedField(
  error: Error | null,
  sentKeys: readonly string[],
): { key: string; field: SpeakerField; message: string } | null {
  if (!(error instanceof ApiError) || error.status !== 422) {
    return null;
  }
  const field = error.details.field;
  const match = typeof field === 'string' ? /^speakers\[(\d+)\]\.(\w+)$/.exec(field) : null;
  const key = match ? sentKeys[Number(match[1])] : undefined;
  if (!match || key === undefined) {
    return null;
  }
  const name = match[2];
  return {
    key,
    field: name === 'name' || name === 'meeting_role' ? name : 'pick',
    message: error.message,
  };
}

/** A refusal meaning the transcript's answers changed elsewhere: reload them, never retry. */
export function isStaleSpeakers(error: Error | null): error is ApiError {
  return (
    error instanceof ApiError &&
    (error.code === 'SPEAKERS_CHANGED' || error.code === 'PERSON_CHANGED')
  );
}

/** How many of a transcript's speakers someone has answered for or linked to a participant. */
export function confirmedCount(transcript: TranscriptSpeakers): number {
  return transcript.speakers.filter((speaker) => speaker.status !== 'unconfirmed').length;
}
