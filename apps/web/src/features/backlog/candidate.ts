import type { DiffKind } from '@/components/DiffTag';
import type { ChangeSet } from '@/features/change-control';

import type { BacklogItem, BacklogVersion, Decision } from './types';

/** A version in review is a change candidate (ADR 0011): a draft is never in review. */
export function isCandidate(version: BacklogVersion): boolean {
  return version.state === 'in_review';
}

const ITEM_DIFF: Record<ChangeSet['operations'][number]['kind'], DiffKind> = {
  add_item: 'added',
  modify_item: 'changed',
  remove_item: 'removed',
};

/** What the server's comparison says happened to each item; unlisted items are unchanged. */
export function diffByItem(changeSet: ChangeSet): Map<string, DiffKind> {
  return new Map(
    changeSet.operations.map((operation) => [operation.item_id, ITEM_DIFF[operation.kind]]),
  );
}

/** Items the candidate removes, as they were in the baseline. */
export function removedItems(changeSet: ChangeSet): BacklogItem[] {
  return changeSet.operations.flatMap((operation) =>
    operation.kind === 'remove_item' && operation.before ? [operation.before] : [],
  );
}

export type ExclusionOutcome = 'pending' | 'reversed' | 'kept';

/**
 * Whether the exclusions the candidate takes back are gone: only once an approver reverses every
 * scope decision on an exclusion; one kept keeps them all, since the candidate can then only be
 * rejected.
 */
export function exclusionOutcome(changeSet: ChangeSet, decisions: Decision[]): ExclusionOutcome {
  const answers = changeSet.scope_decisions
    .filter((reversal) => reversal.reverses === 'exclusion')
    .map(
      (reversal) =>
        decisions.find((decision) => decision.id === reversal.decision_id)?.answer ?? null,
    );
  if (answers.includes('keep')) {
    return 'kept';
  }
  return answers.length > 0 && answers.every((answer) => answer === 'reverse')
    ? 'reversed'
    : 'pending';
}

/** The candidate's own name: the baseline number it would become. */
export function candidateName(baseNumber: number | null): string {
  return baseNumber === null ? 'Candidate' : `Candidate v${String(baseNumber + 1)}`;
}

export type ScopeReadiness = 'made' | 'pending' | 'kept';

/**
 * Whether a candidate's scope decisions allow approval (ADR 0011): made once every one is
 * reversed, pending while any is open, kept as soon as one keeps the earlier scope, which leaves
 * only rejection. A candidate without scope decisions is ready on this count.
 */
export function scopeReadiness(decisions: Decision[]): ScopeReadiness {
  const scope = decisions.filter((decision) => decision.kind === 'scope_reversal');
  if (scope.some((decision) => decision.status === 'answered' && decision.answer === 'keep')) {
    return 'kept';
  }
  return scope.every((decision) => decision.status === 'answered') ? 'made' : 'pending';
}
