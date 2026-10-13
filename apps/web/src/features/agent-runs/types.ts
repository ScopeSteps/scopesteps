import type { components } from '@scopesteps/api-client';

export type Run = components['schemas']['RunResponse'];
export type Question = components['schemas']['ClarificationQuestion'];
export type RunStatus = Run['status'];

/** The API's limit on one answer (POC Implementation Plan, scope contract). */
export const MAX_ANSWER_CHARS = 2000;

export function runQueryKey(runId: string) {
  return ['agent-runs', runId] as const;
}

export function canAdvance(run: Run): boolean {
  return run.status === 'created' || run.status === 'running';
}
