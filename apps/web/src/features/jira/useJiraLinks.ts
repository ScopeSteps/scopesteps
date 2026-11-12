import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { jiraKeys } from './types';
import type { JiraLinks } from './types';

/** The Jira issue of each published item, by item id; empty before the first publish. */
export function useJiraLinks(projectId: string) {
  return useQuery({
    queryKey: jiraKeys(projectId).issues,
    queryFn: async (): Promise<JiraLinks> => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/jira/issues', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return Object.fromEntries(data.issues.map((issue) => [issue.item_id, issue]));
    },
  });
}
