import type { components } from '@scopesteps/api-client';

export type ChangeImpact = components['schemas']['ChangeImpactResponse'];
export type ScopeCount = components['schemas']['ScopeCountResponse'];
export type ImpactKind = 'epics' | 'stories' | 'criteria';

/** The kinds of work in the order they are shown. */
export const IMPACT_KINDS: { key: ImpactKind; label: string }[] = [
  { key: 'epics', label: 'Epics' },
  { key: 'stories', label: 'Stories' },
  { key: 'criteria', label: 'Acceptance criteria' },
];

function count(value: number): string {
  return value === 0 ? 'none' : String(value);
}

function noun(value: number, one: string, many: string): string {
  return value === 1 ? one : many;
}

export function touches(scope: ScopeCount): boolean {
  return scope.added + scope.changed + scope.removed > 0;
}

/**
 * The impact in plain words, from the server's figures only: "Adds 2 stories, changes 1,
 * removes none. Raises 1 scope decision." Epics and criteria are named only when they change.
 */
export function describeImpact(impact: ChangeImpact): string {
  const { stories, epics, criteria } = impact;
  const sentences = [
    touches(stories)
      ? `Adds ${count(stories.added)} ${noun(stories.added, 'story', 'stories')}, changes ${count(stories.changed)}, removes ${count(stories.removed)}.`
      : 'Changes no stories.',
  ];
  if (touches(epics)) {
    sentences.push(
      `Epics: ${count(epics.added)} added, ${count(epics.changed)} changed, ${count(epics.removed)} removed.`,
    );
  }
  if (touches(criteria)) {
    sentences.push(
      `Acceptance criteria: ${count(criteria.added)} added, ${count(criteria.changed)} changed, ${count(criteria.removed)} removed.`,
    );
  }
  if (impact.scope_decisions > 0) {
    sentences.push(
      `Raises ${String(impact.scope_decisions)} scope ${noun(impact.scope_decisions, 'decision', 'decisions')}.`,
    );
  }
  return sentences.join(' ');
}

/** One kind's figures in words: "3 before, 3 after: 1 unchanged, 1 changed, …". */
export function describeCount(scope: ScopeCount): string {
  return (
    `${String(scope.before)} before, ${String(scope.after)} after: ` +
    `${String(scope.unchanged)} unchanged, ${String(scope.changed)} changed, ` +
    `${String(scope.removed)} removed, ${String(scope.added)} added.`
  );
}
