import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { jiraKeys } from './types';

/** What publishing the version would do now. Asks the server only; nothing reaches Jira. */
export function useJiraPreview(projectId: string, versionId: string) {
  return useQuery({
    queryKey: jiraKeys(projectId).preview(versionId),
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/jira/preview',
        { params: { path: { project_id: projectId }, query: { version_id: versionId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // A preview is only true for the moment it is asked; opening the window again asks again.
    gcTime: 0,
    staleTime: 0,
  });
}
