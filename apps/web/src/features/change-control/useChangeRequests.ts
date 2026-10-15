import { useInfiniteQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { changeRequestsQueryKey } from './types';
import type { ChangeRequest } from './types';

const PAGE_SIZE = 20;
// A request is analysed in under a minute; a slow look is enough for the list.
const WATCH_INTERVAL_MS = 5000;

/**
 * The project's change requests, newest first, a page at a time with older pages on demand.
 * Reloads while any request on the first page is still being analysed.
 */
export function useChangeRequests(projectId: string) {
  const query = useInfiniteQuery({
    queryKey: changeRequestsQueryKey(projectId),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/change-requests',
        {
          params: {
            path: { project_id: projectId },
            query:
              pageParam === null ? { limit: PAGE_SIZE } : { limit: PAGE_SIZE, cursor: pageParam },
          },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: (current) =>
      current.state.data?.pages[0]?.change_requests.some(
        (request) => request.status === 'analyzing',
      )
        ? WATCH_INTERVAL_MS
        : false,
  });
  const requests: ChangeRequest[] = query.data?.pages.flatMap((page) => page.change_requests) ?? [];
  return { ...query, requests };
}
