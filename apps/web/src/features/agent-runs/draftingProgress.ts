import type { Run } from './types';

/**
 * Where a draft written in steps has got (ADR 0028): its outline first, then one epic at a time.
 * Null when the run is not writing one, so the caller keeps its own wording.
 */
export function draftingText(run: Run): string | null {
  const progress = run.drafting;
  if (!progress) {
    return null;
  }
  if (!progress.outline_written) {
    return 'Writing the outline of epics…';
  }
  if (progress.epics_written >= progress.epics) {
    return 'Putting the backlog together…';
  }
  return `Writing epic ${String(progress.epics_written + 1)} of ${String(progress.epics)}…`;
}
