import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export function sourcesQueryKey(projectId: string) {
  return ['sources', projectId, 'list'] as const;
}

export function useSources(projectId: string) {
  return useQuery({
    queryKey: sourcesQueryKey(projectId),
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/sources', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data.source_versions;
    },
  });
}
