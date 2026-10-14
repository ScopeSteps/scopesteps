import { describe, expect, it } from 'vitest';

import { setupSteps } from './setupSteps';

const BASELINE_ID = '019a3a5e-0000-7000-8000-0000000000e9';
const OPEN_ID = '019a3a5e-0000-7000-8000-0000000000e1';

describe('setupSteps', () => {
  it.each([
    ['a new project', false, undefined, ['active', 'todo', 'todo']],
    [
      'stored sources and no draft',
      true,
      {
        state: 'no_baseline',
        baseline_version: null,
        baseline_version_id: null,
        open_version_id: null,
      },
      ['done', 'active', 'todo'],
    ],
    [
      'a draft in review',
      true,
      {
        state: 'draft_in_progress',
        baseline_version: null,
        baseline_version_id: null,
        open_version_id: OPEN_ID,
      },
      ['done', 'done', 'active'],
    ],
    [
      'an approved baseline',
      true,
      {
        state: 'baseline',
        baseline_version: 1,
        baseline_version_id: BASELINE_ID,
        open_version_id: null,
      },
      ['done', 'done', 'done'],
    ],
  ] as const)('marks the steps for %s', (_case, hasSources, status, [sources, run, review]) => {
    expect(setupSteps(hasSources, status)).toEqual({ sources, run, review });
  });
});
