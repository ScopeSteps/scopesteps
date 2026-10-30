import type { components } from '@scopesteps/api-client';

import type { TagTone } from '@/components/Tag';
import { ApiError } from '@/lib/apiError';
import { formatWhen } from '@/lib/formatWhen';

export type BacklogVersion = components['schemas']['BacklogVersionResponse'];
export type BacklogItem = components['schemas']['BacklogItem'];
export type Criterion = components['schemas']['AcceptanceCriterion'];
export type Decision = components['schemas']['BacklogDecision'];
export type ScopeNote = components['schemas']['ScopeNoteResponse'];
export type SetAsideNote = components['schemas']['SetAsideNoteResponse'];
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
export type VersionSummary = components['schemas']['BacklogVersionSummary'];
export type VersionPage = components['schemas']['BacklogVersionPage'];
export type Comparison = components['schemas']['VersionComparisonResponse'];
export type ItemChange = components['schemas']['ItemChangeResponse'];
export type CriterionChange = components['schemas']['CriterionChangeResponse'];

export function versionQueryKey(projectId: string, versionId: string | null) {
  return ['backlog', projectId, 'version', versionId ?? 'none'] as const;
}

/** What paragraphs the agent read as background and cited nowhere else are called. */
export const SET_ASIDE = 'Set aside as context';

/** What the evidence sheet is open on, as it appears in the URL. */
export type ClaimRef =
  | { type: 'criterion'; id: string }
  | { type: 'decision'; id: string }
  | { type: 'scope'; index: number }
  | { type: 'context'; index: number };

export function claimParam(claim: ClaimRef): string {
  return claim.type === 'scope' || claim.type === 'context'
    ? `${claim.type}:${String(claim.index)}`
    : `${claim.type}:${claim.id}`;
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
  return (type === 'scope' || type === 'context') && Number.isInteger(index) && index >= 0
    ? { type, index }
    : null;
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
      error.code === 'VERSION_NOT_IN_REVIEW' ||
      error.code === 'DECISION_ALREADY_ANSWERED' ||
      error.code === 'SUGGESTION_ALREADY_REVIEWED' ||
      error.code === 'BASELINE_CHANGED')
  );
}

/** A version as the selector lists it: from the history, or the version in view meanwhile. */
export type VersionOption = Pick<
  VersionSummary,
  'id' | 'state' | 'revision' | 'number' | 'created_at' | 'base_version_id'
>;

/** How an approved version is named everywhere: by its baseline number, as the server gave it. */
export function versionName(number: number | null): string {
  return number === null ? 'Approved version' : `v${String(number)}`;
}

/** The version in view as an option, numbered when it is the current baseline. */
export function asOption(version: BacklogVersion, status: ScopeStatus | undefined): VersionOption {
  const isBaseline = version.id === status?.baseline_version_id;
  return {
    id: version.id,
    state: version.state,
    revision: version.revision,
    number: isBaseline ? (status.baseline_version ?? null) : null,
    created_at: version.created_at,
    base_version_id: version.base_version_id,
  };
}

/**
 * How a version is named in the version selector. A draft other than the one in progress, and a
 * rejection, carry their creation time, since several can share a revision number.
 */
export function versionLabel(version: VersionOption, status: ScopeStatus | undefined): string {
  const revision = `r${String(version.revision)}`;
  const created = formatWhen(version.created_at);
  switch (version.state) {
    case 'approved':
      return version.id === status?.baseline_version_id
        ? `${versionName(version.number ?? status.baseline_version)} · current baseline`
        : versionName(version.number);
    case 'draft':
      return status?.open_version_id && status.open_version_id !== version.id
        ? `Earlier draft ${revision} · ${created}`
        : `Draft ${revision}`;
    case 'in_review':
      return status?.baseline_version
        ? `Candidate v${String(status.baseline_version + 1)} (in review)`
        : 'Candidate (in review)';
    case 'rejected':
      return version.base_version_id
        ? `Rejected candidate · ${created}`
        : `Draft ${revision} · rejected · ${created}`;
  }
}

/**
 * An item's stable id as a change candidate shows it: its last eight characters, which differ
 * between items (the leading ones are a timestamp shared by a whole version).
 */
export function shortId(id: string): string {
  return id.slice(-8);
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

/** Each epic's and story's open discussions, and how to open them; absent where none show. */
export interface ItemDiscussions {
  counts: Readonly<Record<string, number>>;
  onOpen: (item: { id: string; title: string }) => void;
}
