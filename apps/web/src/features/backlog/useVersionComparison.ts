import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

/**
 * What changes from `base` to `candidate`, as the server compares them by stable ids. Nothing
 * is requested until both are chosen and different.
 */
export function useVersionComparison(
  projectId: string,
  base: string | null,
  candidate: string | null,
) {
  return useQuery({
    queryKey: ['backlog', projectId, 'compare', base, candidate],
    enabled: base !== null && candidate !== null && base !== candidate,
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/backlogs/compare',
        {
          params: {
            path: { project_id: projectId },
            query: { base: base ?? '', candidate: candidate ?? '' },
          },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
