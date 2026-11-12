import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export function dashboardQueryKey(projectId: string) {
  return ['projects', projectId, 'dashboard'] as const;
}

/** The project's figures, read from what the server stores; no AI is involved. */
export function useDashboard(projectId: string) {
  return useQuery({
    queryKey: dashboardQueryKey(projectId),
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/dashboard', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
