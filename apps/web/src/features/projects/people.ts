import type { components } from '@scopesteps/api-client';

import type { TagTone } from '@/components/Tag';
import { ApiError } from '@/lib/apiError';

export type Person = components['schemas']['PersonResponse'];
export type ConfirmableRights = components['schemas']['RightsRequest']['rights'];
export type PersonEvidence = components['schemas']['EvidenceRef'];

// The API's limits on a correction (CorrectionRequest).
export const MAX_NAME = 80;
export const MAX_ROLE = 80;

export function peopleQueryKey(projectId: string) {
  return ['projects', projectId, 'people'] as const;
}

/** Whether nobody can yet say if the person decides: no source states it and nobody confirmed. */
export function rightsOpen(person: Person): boolean {
  return person.extracted.stated_rights === 'not_stated' && person.confirmed_rights === null;
}

/** The people whose decision rights are neither stated in a source nor confirmed. */
export function openRightsCount(people: readonly Person[] | undefined): number {
  return people?.filter(rightsOpen).length ?? 0;
}

export interface RightsSummary {
  tag: string;
  tone: TagTone;
  text: string;
}

/** What the card says about a person's decision rights, and where that comes from. */
export function rightsSummary(person: Person): RightsSummary {
  switch (person.extracted.stated_rights) {
    case 'decides':
      return { tag: 'Stated in source', tone: 'accent', text: 'Decides what’s in scope.' };
    case 'advises':
      return { tag: 'Stated in source', tone: 'accent', text: 'Advises on scope.' };
    case 'not_stated':
      break;
  }
  switch (person.confirmed_rights?.rights) {
    case 'decides':
      return { tag: 'Confirmed', tone: 'ok', text: 'Can decide what’s in scope.' };
    case 'advises':
      return { tag: 'Confirmed', tone: 'ok', text: 'Advises only.' };
    case 'unknown':
      return {
        tag: 'Checked',
        tone: 'neutral',
        text: 'Your team could not say whether they decide scope.',
      };
    case undefined:
      return {
        tag: 'Not stated',
        tone: 'warn',
        text: 'No source states their decision rights.',
      };
  }
}

/**
 * A refusal that means the person on screen is out of date: someone else changed them, or a
 * later run found a source that states their rights. The page offers a reload, never a retry.
 */
export function isStalePerson(error: Error | null): error is ApiError {
  return (
    error instanceof ApiError &&
    (error.code === 'PERSON_CHANGED' || error.code === 'RIGHTS_STATED_IN_SOURCE')
  );
}
