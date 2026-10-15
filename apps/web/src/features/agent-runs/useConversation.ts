import { useInfiniteQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { conversationQueryKey } from './types';
import type { Message } from './types';

// The agent's steps take 10 to 30 seconds, so a slower look is enough for someone watching.
const WATCH_INTERVAL_MS = 5000;
const PAGE_SIZE = 30;

/**
 * The project's conversation, a page of the newest messages first, with older pages loaded on
 * demand. `watch` reloads it while the agent works, for someone who does not drive the run.
 */
export function useConversation(projectId: string, { watch = false } = {}) {
  const query = useInfiniteQuery({
    queryKey: conversationQueryKey(projectId),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/messages', {
        params: {
          path: { project_id: projectId },
          query:
            pageParam === null ? { limit: PAGE_SIZE } : { limit: PAGE_SIZE, cursor: pageParam },
        },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    refetchInterval: (current) => {
      const active = current.state.data?.pages[0]?.active_run;
      return watch && (active?.status === 'created' || active?.status === 'running')
        ? WATCH_INTERVAL_MS
        : false;
    },
  });

  const pages = query.data?.pages ?? [];
  // Pages and messages come newest first; the thread reads oldest first.
  const messages: Message[] = pages.flatMap((page) => page.messages).reverse();
  return {
    ...query,
    messages,
    activeRun: pages[0]?.active_run ?? null,
  };
}
