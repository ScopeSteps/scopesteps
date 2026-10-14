import type { components } from '@scopesteps/api-client';

import type { TagTone } from '@/components/Tag';
import { ApiError } from '@/lib/apiError';

export type BacklogVersion = components['schemas']['BacklogVersionResponse'];
export type BacklogItem = components['schemas']['BacklogItem'];
export type Criterion = components['schemas']['AcceptanceCriterion'];
export type Decision = components['schemas']['BacklogDecision'];
export type ScopeNote = components['schemas']['ScopeNoteResponse'];
export type EvidenceRef = components['schemas']['EvidenceRef'];
export type Blocker = components['schemas']['Blocker'];
export type ClaimOrigin = Criterion['origin'];
export type SuggestionStatus = NonNullable<Criterion['suggestion']>;
export type ItemPatch = Omit<components['schemas']['ItemPatchRequest'], 'expected_revision'>;
export type CriterionPatch = components['schemas']['CriterionPatch'];
export type Review = components['schemas']['ReviewResponse'];
export type Check = components['schemas']['CheckResponse'];
export type ApprovalDecision = components['schemas']['DecisionResponse'];
export type ScopeStatus = components['schemas']['ScopeStatusResponse'];

export function versionQueryKey(projectId: string, versionId: string | null) {
  return ['backlog', projectId, 'version', versionId ?? 'none'] as const;
}

/** What the evidence sheet is open on, as it appears in the URL. */
export type ClaimRef =
  | { type: 'criterion'; id: string }
  | { type: 'decision'; id: string }
  | { type: 'scope'; index: number };

export function claimParam(claim: ClaimRef): string {
  return claim.type === 'scope' ? `scope:${String(claim.index)}` : `${claim.type}:${claim.id}`;
}

export function parseClaimParam(value: string | null): ClaimRef | null {
  const [type, rest] = value?.split(':', 2) ?? [];
  if (!rest) {
    return null;
  }
  if (type === 'criterion' || type === 'decision') {
    return { type, id: rest };
  }
  const index = Number(rest);
  return type === 'scope' && Number.isInteger(index) && index >= 0 ? { type, index } : null;
}

export const ORIGINS: Record<ClaimOrigin, { label: string; tone: TagTone }> = {
  source: { label: 'Source-backed', tone: 'ok' },
  human: { label: 'Confirmed by an answer', tone: 'neutral' },
  proposed: { label: 'Agent suggestion · no source', tone: 'warn' },
  person: { label: 'Added by a person', tone: 'neutral' },
};

/** An agent suggestion's review status; null for a criterion that is not a suggestion. */
export function suggestionStatus(criterion: Criterion): SuggestionStatus | null {
  return criterion.origin === 'proposed' ? (criterion.suggestion ?? 'pending') : null;
}

/** The tags a criterion carries: where it comes from, and whether a person rewrote it. */
export function criterionTags(criterion: Criterion): { label: string; tone: TagTone }[] {
  switch (suggestionStatus(criterion)) {
    case 'pending':
      return [ORIGINS.proposed];
    case 'accepted':
      return [{ label: 'Suggestion · accepted', tone: 'warn' }];
    case 'rejected':
      return [{ label: 'Rejected', tone: 'neutral' }];
    case null:
      break;
  }
  const origin = ORIGINS[criterion.origin];
  return criterion.edited_by && criterion.origin !== 'person'
    ? [origin, { label: 'Edited', tone: 'neutral' }]
    : [origin];
}

/** A draft edit that changes only one suggestion's status, keeping every criterion as it is. */
export function reviewSuggestion(
  item: BacklogItem,
  criterionId: string,
  status: SuggestionStatus,
): ItemPatch {
  return {
    criteria: item.criteria.map((criterion) => ({
      id: criterion.id,
      text: criterion.text,
      suggestion: criterion.id === criterionId ? status : null,
    })),
  };
}

/**
 * The API's answer that what this page shows is out of date: another edit moved the revision,
 * or the version was approved or rejected meanwhile. Reload and review again; never retry.
 */
export function isStale(error: Error | null): error is ApiError {
  return (
    error instanceof ApiError &&
    (error.code === 'VERSION_CHANGED' ||
      error.code === 'VERSION_NOT_DRAFT' ||
      error.code === 'BASELINE_CHANGED')
  );
}

/** How a version is named in the version selector. */
export function versionLabel(version: BacklogVersion, status: ScopeStatus | undefined): string {
  const revision = `r${String(version.revision)}`;
  switch (version.state) {
    case 'approved':
      return version.id === status?.baseline_version_id && status.baseline_version !== null
        ? `v${String(status.baseline_version)} · current baseline`
        : 'Approved version';
    case 'draft':
      return status?.open_version_id && status.open_version_id !== version.id
        ? `Earlier draft ${revision}`
        : `Draft ${revision}`;
    case 'in_review':
      return `Draft ${revision} · in review`;
    case 'rejected':
      return `Draft ${revision} · rejected`;
  }
}

/** The first and last four characters, as the prototype shows a content hash. */
export function shortHash(hash: string): string {
  return `${hash.slice(0, 4)}…${hash.slice(-4)}`;
}

/** A newly saved candidate is revision 1; every saved edit or answer moves the revision. */
export function hasEdits(version: BacklogVersion): boolean {
  return version.state === 'draft' && version.revision > 1;
}

export function decisionLabel(decision: Decision): string {
  if (decision.status === 'answered') {
    return 'Answered';
  }
  const kind = decision.kind === 'conflict' ? 'Conflict' : 'Open decision';
  return decision.status === 'skipped' ? `${kind} · skipped, still open` : kind;
}

/** A suggestion waits for review; every other blocker waits on a decision. */
export function isSuggestion(blocker: Blocker): boolean {
  return blocker.code === 'proposed_criterion';
}

export interface Attention {
  blocked: number;
  suggestions: number;
}

export function attention(blockers: readonly Blocker[]): Attention {
  const suggestions = blockers.filter(isSuggestion).length;
  return { blocked: blockers.length - suggestions, suggestions };
}

export function isUnderReview(version: BacklogVersion): boolean {
  return version.state === 'draft' || version.state === 'in_review';
}
