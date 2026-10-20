import { describe, expect, it } from 'vitest';

import { setupSteps } from './setupSteps';

const BASELINE_ID = '019a3a5e-0000-7000-8000-0000000000e9';
const OPEN_ID = '019a3a5e-0000-7000-8000-0000000000e1';
const NO_DRAFT = {
  state: 'no_baseline',
  baseline_version: null,
  baseline_version_id: null,
  open_version_id: null,
} as const;
const IN_REVIEW = {
  state: 'draft_in_progress',
  baseline_version: null,
  baseline_version_id: null,
  open_version_id: OPEN_ID,
} as const;
const APPROVED = {
  state: 'baseline',
  baseline_version: 1,
  baseline_version_id: BASELINE_ID,
  open_version_id: null,
} as const;

describe('setupSteps', () => {
  it.each([
    ['a new project', false, 0, undefined, ['active', 'todo', 'todo', 'todo']],
    ['sources with speakers to identify', true, 2, NO_DRAFT, ['done', 'active', 'todo', 'todo']],
    ['speakers still loading', true, undefined, NO_DRAFT, ['done', 'active', 'todo', 'todo']],
    ['every speaker identified', true, 0, NO_DRAFT, ['done', 'done', 'active', 'todo']],
    ['a draft in review', true, 0, IN_REVIEW, ['done', 'done', 'done', 'active']],
    ['a new transcript after a draft', true, 1, IN_REVIEW, ['done', 'active', 'done', 'active']],
    ['an approved baseline', true, 0, APPROVED, ['done', 'done', 'done', 'done']],
  ] as const)(
    'marks the steps for %s',
    (_case, hasSources, unconfirmed, status, [sources, people, run, review]) => {
      expect(setupSteps(hasSources, unconfirmed, status)).toEqual({
        sources,
        people,
        run,
        review,
      });
    },
  );
});
