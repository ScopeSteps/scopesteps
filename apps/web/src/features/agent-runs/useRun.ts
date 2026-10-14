import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { canAdvance, runQueryKey } from './types';

// The agent's steps take 10 to 30 seconds, so a slower look is enough for someone watching.
const WATCH_INTERVAL_MS = 5000;

interface RunOptions {
  /**
   * Reload the run while the agent works on it. For someone who cannot advance the run
   * themselves (a viewer), so they see an editor's progress.
   */
  watch?: boolean;
}

/** The persisted run. Disabled until there is a run to load. */
export function useRun(runId: string | null, { watch = false }: RunOptions = {}) {
  return useQuery({
    queryKey: runQueryKey(runId ?? 'none'),
    enabled: runId !== null,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/runs/{run_id}', {
        params: { path: { run_id: runId ?? '' } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    refetchInterval: (query) => {
      const run = query.state.data;
      return watch && run && canAdvance(run) ? WATCH_INTERVAL_MS : false;
    },
  });
}
