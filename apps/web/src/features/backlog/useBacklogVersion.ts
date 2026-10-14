import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { versionQueryKey } from './types';

/** One backlog version. Disabled until there is a version to load. */
export function useBacklogVersion(projectId: string, versionId: string | null) {
  return useQuery({
    queryKey: versionQueryKey(projectId, versionId),
    enabled: versionId !== null,
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/backlogs/{version_id}',
        { params: { path: { project_id: projectId, version_id: versionId ?? '' } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
