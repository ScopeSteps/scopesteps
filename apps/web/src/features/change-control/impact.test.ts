import { describe, expect, it } from 'vitest';

import { describeImpact } from './impact';
import type { ChangeImpact, ScopeCount } from './impact';

function scope(overrides: Partial<ScopeCount> = {}): ScopeCount {
  return { before: 0, after: 0, added: 0, changed: 0, removed: 0, unchanged: 0, ...overrides };
}

function impact(overrides: Partial<ChangeImpact> = {}): ChangeImpact {
  return {
    epics: scope({ before: 1, after: 1, unchanged: 1 }),
    stories: scope(),
    criteria: scope(),
    scope_decisions: 0,
    ...overrides,
  };
}

describe('describeImpact', () => {
  it('says what happens to the stories and which scope decisions the change raises', () => {
    const stories = scope({ before: 3, after: 5, added: 2, changed: 1, unchanged: 2 });

    expect(describeImpact(impact({ stories, scope_decisions: 1 }))).toBe(
      'Adds 2 stories, changes 1, removes none. Raises 1 scope decision.',
    );
  });

  it('names epics and criteria only when the change touches them', () => {
    const result = describeImpact(
      impact({
        stories: scope({ before: 1, after: 1, added: 1, removed: 1 }),
        epics: scope({ before: 1, after: 2, added: 1, unchanged: 1 }),
        criteria: scope({ before: 4, after: 4, added: 1, changed: 2, removed: 1, unchanged: 1 }),
        scope_decisions: 2,
      }),
    );

    expect(result).toBe(
      'Adds 1 story, changes none, removes 1. Epics: 1 added, none changed, none removed. ' +
        'Acceptance criteria: 1 added, 2 changed, 1 removed. Raises 2 scope decisions.',
    );
  });

  it('says plainly when no story changes', () => {
    const criteria = scope({ before: 2, after: 2, changed: 1, unchanged: 1 });

    expect(describeImpact(impact({ criteria }))).toBe(
      'Changes no stories. Acceptance criteria: none added, 1 changed, none removed.',
    );
  });
});
