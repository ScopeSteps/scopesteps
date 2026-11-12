import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { jiraKeys } from './types';
import type { JiraPublish } from './types';

/** How often the page looks again while the server's background sender works on a publish. */
export const PUBLISH_POLL_MS = 2000;

export function isSending(publish: JiraPublish): boolean {
  return publish.status === 'sending';
}

/**
 * The project's newest publishes, for someone who may publish. While one is sending, the list
 * is fetched again every few seconds; the server sends it whether or not the page is open.
 */
export function useJiraPublishes(projectId: string, enabled: boolean) {
  const queryClient = useQueryClient();
  const keys = jiraKeys(projectId);
  return useQuery({
    queryKey: keys.publishes,
    enabled,
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/jira/publishes',
        { params: { path: { project_id: projectId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      const before = queryClient.getQueryData<JiraPublish[]>(keys.publishes) ?? [];
      const finished = before.some(
        (earlier) =>
          isSending(earlier) &&
          data.publishes.some((now) => now.id === earlier.id && !isSending(now)),
      );
      if (finished) {
        // The items it published now have Jira keys, and a refused token shows in settings.
        void queryClient.invalidateQueries({ queryKey: keys.issues });
        void queryClient.invalidateQueries({ queryKey: keys.connection });
      }
      return data.publishes;
    },
    refetchInterval: (query) =>
      query.state.data?.some(isSending) === true ? PUBLISH_POLL_MS : false,
  });
}
