import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export function useSourceBlocks(projectId: string, sourceVersionId: string) {
  return useQuery({
    queryKey: ['sources', projectId, 'blocks', sourceVersionId],
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/sources/{source_version_id}/blocks',
        { params: { path: { project_id: projectId, source_version_id: sourceVersionId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // A source version is immutable, so its blocks never go stale.
    staleTime: Infinity,
  });
}
