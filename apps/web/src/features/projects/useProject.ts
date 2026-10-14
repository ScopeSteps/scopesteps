import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

/** The project with its name, the actor's roles and the limits the server applies. */
export function useProject(projectId: string) {
  return useQuery({
    queryKey: ['projects', projectId, 'detail'],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
