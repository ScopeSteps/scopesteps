import type { components } from '@scopesteps/api-client';

export type StepState = 'done' | 'active' | 'todo';
type ScopeStatus = components['schemas']['ScopeStatusResponse'];

/**
 * Where the project stands on each setup step, from its sources and the scope status the API
 * reports: a draft or a baseline means a run has finished, a baseline with nothing newer in
 * review means the last draft was approved.
 */
export function setupSteps(
  hasSources: boolean,
  status: ScopeStatus | undefined,
): { sources: StepState; run: StepState; review: StepState } {
  const drafted =
    status !== undefined && (status.open_version_id !== null || status.baseline_version !== null);
  const approved = status?.state === 'baseline';
  return {
    sources: hasSources ? 'done' : 'active',
    run: drafted ? 'done' : hasSources ? 'active' : 'todo',
    review: approved ? 'done' : drafted ? 'active' : 'todo',
  };
}
