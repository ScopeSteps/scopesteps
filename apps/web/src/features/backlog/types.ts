import type { components } from '@scopesteps/api-client';

import type { TagTone } from '@/components/Tag';

export type BacklogVersion = components['schemas']['BacklogVersionResponse'];
export type BacklogItem = components['schemas']['BacklogItem'];
export type Criterion = components['schemas']['AcceptanceCriterion'];
export type Decision = components['schemas']['BacklogDecision'];
export type ScopeNote = components['schemas']['ScopeNoteResponse'];
export type EvidenceRef = components['schemas']['EvidenceRef'];
export type Blocker = components['schemas']['Blocker'];
export type ClaimOrigin = Criterion['origin'];

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
};

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
