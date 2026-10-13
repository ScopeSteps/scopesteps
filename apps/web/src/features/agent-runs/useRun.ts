import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { runQueryKey } from './types';

/** The persisted run. Disabled until there is a run to load. */
export function useRun(runId: string | null) {
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
  });
}
