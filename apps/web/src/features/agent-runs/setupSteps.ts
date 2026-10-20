import type { components } from '@scopesteps/api-client';

export type StepState = 'done' | 'active' | 'todo';
type ScopeStatus = components['schemas']['ScopeStatusResponse'];

export interface SetupSteps {
  sources: StepState;
  people: StepState;
  run: StepState;
  review: StepState;
}

/**
 * Where the project stands on each setup step, from its sources, the speakers nobody has said
 * who they are (undefined while loading) and the scope status the API reports. A draft or a
 * baseline means a run has finished, a baseline with nothing newer in review means the last
 * draft was approved. A run can start only once every speaker is confirmed (ADR 0015), so the
 * people step stays active whenever a transcript brings new ones, even after a draft.
 */
export function setupSteps(
  hasSources: boolean,
  unconfirmedSpeakers: number | undefined,
  status: ScopeStatus | undefined,
): SetupSteps {
  const drafted =
    status !== undefined && (status.open_version_id !== null || status.baseline_version !== null);
  const approved = status?.state === 'baseline';
  const peopleKnown = hasSources && unconfirmedSpeakers === 0;
  return {
    sources: hasSources ? 'done' : 'active',
    people: peopleKnown ? 'done' : hasSources ? 'active' : 'todo',
    run: drafted ? 'done' : peopleKnown ? 'active' : 'todo',
    review: approved ? 'done' : drafted ? 'active' : 'todo',
  };
}
