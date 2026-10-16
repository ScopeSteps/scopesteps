import type { QueryClient } from '@tanstack/react-query';

import { canAdvance } from './types';
import type { Run } from './types';

/**
 * When a run stops working (ready for review, waiting for answers, failed, stopped), the server
 * has saved or dropped its draft, so the project's scope state and its versions moved on too.
 * Reloads them before the new run state is shown, so the page never pairs the new run with the
 * old scope (a false "Locked" note, a header still offering to start the run).
 */
export async function refreshAfterRunMoved(
  queryClient: QueryClient,
  previous: Run | undefined,
  next: Run,
): Promise<void> {
  if (previous === undefined || previous.status === next.status || canAdvance(next)) {
    return;
  }
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ['projects'] }),
    queryClient.invalidateQueries({ queryKey: ['backlog'] }),
    queryClient.invalidateQueries({ queryKey: ['change-control'] }),
  ]);
}
