import type { components } from '@scopesteps/api-client';

export type BacklogVersion = components['schemas']['BacklogVersionResponse'];
export type BacklogItem = components['schemas']['BacklogItem'];
export type Criterion = components['schemas']['AcceptanceCriterion'];
export type Decision = components['schemas']['BacklogDecision'];
export type ScopeNote = components['schemas']['ScopeNoteResponse'];
export type EvidenceRef = components['schemas']['EvidenceRef'];
export type Blocker = components['schemas']['Blocker'];
export type ClaimOrigin = Criterion['origin'];

/** What the evidence drawer is open on, as it appears in the URL. */
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

export const ORIGIN_LABELS: Record<ClaimOrigin, string> = {
  source: 'Source-backed',
  human: 'Reviewer-confirmed',
  proposed: 'AI-proposed: needs review',
};

export function decisionLabel(decision: Decision): string {
  if (decision.status === 'answered') {
    return 'Answered';
  }
  const kind = decision.kind === 'conflict' ? 'Conflict' : 'Open decision';
  return decision.status === 'skipped' ? `${kind}: skipped, still unresolved` : kind;
}
