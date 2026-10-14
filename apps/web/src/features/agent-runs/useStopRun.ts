import { useRef } from 'react';

import { useRunCommand } from './useRunCommand';

/** Cancels a run. One key per run, so however often Stop is pressed, the API stops it once. */
export function useStopRun(runId: string) {
  const { mutate, isPending, error } = useRunCommand(runId);
  // Set synchronously, so a double click cannot send before the disabled state has rendered.
  const inFlight = useRef(false);

  function stop() {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    mutate(
      { command: { type: 'cancel' }, idempotencyKey: `cancel-${runId}` },
      {
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  }

  return { stop, isPending, error };
}
