import { describe, expect, it } from 'vitest';

import { projectStatusText } from './projectStatusText';

const NO_IDS = { baseline_version_id: null, open_version_id: null };

describe('projectStatusText', () => {
  it.each([
    [{ state: 'no_baseline', baseline_version: null }, 'Nothing approved yet'],
    [{ state: 'draft_in_progress', baseline_version: null }, 'Draft in progress'],
    [{ state: 'draft_in_progress', baseline_version: 2 }, 'Draft in progress'],
    [{ state: 'candidate_in_review', baseline_version: 2 }, 'Proposed v3 in review'],
    [{ state: 'candidate_in_review', baseline_version: null }, 'Proposed version in review'],
    [{ state: 'baseline', baseline_version: 1 }, 'v1 approved'],
  ] as const)('describes %j as "%s"', (status, text) => {
    expect(projectStatusText({ ...NO_IDS, ...status })).toBe(text);
  });
});
