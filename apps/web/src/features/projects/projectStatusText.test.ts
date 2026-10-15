import { describe, expect, it } from 'vitest';

import { projectStatusText } from './projectStatusText';

const NO_IDS = { baseline_version_id: null, open_version_id: null };

describe('projectStatusText', () => {
  it.each([
    [{ state: 'no_baseline', baseline_version: null }, 'No baseline yet'],
    [{ state: 'draft_in_progress', baseline_version: null }, 'Draft in progress'],
    [{ state: 'draft_in_progress', baseline_version: 2 }, 'Draft in progress'],
    [{ state: 'candidate_in_review', baseline_version: 2 }, 'Candidate v3 in review'],
    [{ state: 'candidate_in_review', baseline_version: null }, 'Candidate in review'],
    [{ state: 'baseline', baseline_version: 1 }, 'Baseline v1 approved'],
  ] as const)('describes %j as "%s"', (status, text) => {
    expect(projectStatusText({ ...NO_IDS, ...status })).toBe(text);
  });
});
