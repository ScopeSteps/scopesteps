import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export function useBacklogVersion(projectId: string, versionId: string) {
  return useQuery({
    queryKey: ['backlog', projectId, 'version', versionId],
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/backlogs/{version_id}',
        { params: { path: { project_id: projectId, version_id: versionId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
