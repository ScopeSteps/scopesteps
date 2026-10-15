import type { components } from '@scopesteps/api-client';

import type { TagTone } from '@/components/Tag';

export type ChangeRequest = components['schemas']['ChangeRequestResponse'];
export type ChangeRequestStatus = ChangeRequest['status'];
export type ChangeRequestPage = components['schemas']['ChangeRequestPage'];
export type ChangeSet = components['schemas']['ChangeSetResponse'];
export type ScopeReversal = components['schemas']['ScopeReversalResponse'];

export function changeRequestsQueryKey(projectId: string) {
  return ['change-control', projectId, 'change-requests'] as const;
}

export function changeRequestQueryKey(changeRequestId: string | null) {
  return ['change-control', 'change-request', changeRequestId ?? 'none'] as const;
}

export function changeSetQueryKey(versionId: string | null) {
  return ['change-control', 'change-set', versionId ?? 'none'] as const;
}

/** How a change request is named everywhere, from the number the server gave it. */
export function changeRequestName(number: number): string {
  return `CR-${String(number)}`;
}

/** Every status the API reports, failed included, with its tag. */
export const STATUSES: Record<ChangeRequestStatus, { label: string; tone: TagTone }> = {
  analyzing: { label: 'Analyzing…', tone: 'accent' },
  in_review: { label: 'In review', tone: 'warn' },
  no_change_needed: { label: 'No change needed', tone: 'neutral' },
  approved: { label: 'Approved', tone: 'ok' },
  rejected: { label: 'Rejected', tone: 'neutral' },
  failed: { label: 'Failed', tone: 'bad' },
};
