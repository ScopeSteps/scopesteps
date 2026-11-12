import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { jiraKeys } from './types';

/** Whether the project is connected to Jira, and whether you may publish or manage it. */
export function useJiraConnection(projectId: string) {
  return useQuery({
    queryKey: jiraKeys(projectId).connection,
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/jira/connection',
        { params: { path: { project_id: projectId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
