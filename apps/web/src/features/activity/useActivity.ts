import { useInfiniteQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export function activityQueryKey(projectId: string) {
  return ['activity', projectId, 'feed'] as const;
}

const FIRST_PAGE: string | null = null;

/** The project's activity log, newest first, one server page at a time. */
export function useActivity(projectId: string) {
  return useInfiniteQuery({
    queryKey: activityQueryKey(projectId),
    initialPageParam: FIRST_PAGE,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/activity', {
        params: {
          path: { project_id: projectId },
          query: pageParam === null ? {} : { cursor: pageParam },
        },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    getNextPageParam: (page) => page.next_cursor,
  });
}
