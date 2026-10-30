import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import type { DiscussionScope, Thread, ThreadFilter } from './types';

export function discussionsKey(projectId: string) {
  return ['discussions', projectId] as const;
}

/** A scope's threads, newest activity first, a page at a time. */
export function useThreads(projectId: string, scope: DiscussionScope, filter: ThreadFilter) {
  return useInfiniteQuery({
    queryKey: [...discussionsKey(projectId), 'threads', scope, filter],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/threads', {
        params: {
          path: { project_id: projectId },
          query: {
            item_id: scope.kind === 'item' ? scope.itemId : null,
            status: filter,
            cursor: pageParam,
          },
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

/** Open threads per epic or story, for the backlog's speech bubbles. */
export function useThreadCounts(projectId: string) {
  return useQuery({
    queryKey: [...discussionsKey(projectId), 'counts'],
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/projects/{project_id}/threads/counts',
        { params: { path: { project_id: projectId } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}

export type DiscussionCommand =
  | { type: 'start'; itemId: string | null; body: string }
  | { type: 'reply'; threadId: string; body: string }
  | { type: 'edit'; commentId: string; body: string; expectedRevision: number }
  | { type: 'delete'; commentId: string }
  | { type: 'resolve' | 'reopen'; threadId: string; expectedRevision: number };

async function send(
  projectId: string,
  command: DiscussionCommand,
  key: string,
): Promise<Thread | null> {
  const header = { 'Idempotency-Key': key };
  const result = await (() => {
    switch (command.type) {
      case 'start':
        return api.POST('/api/v1/projects/{project_id}/threads', {
          params: { path: { project_id: projectId }, header },
          body: { item_id: command.itemId, body: command.body },
        });
      case 'reply':
        return api.POST('/api/v1/threads/{thread_id}/comments', {
          params: { path: { thread_id: command.threadId }, header },
          body: { body: command.body },
        });
      case 'edit':
        return api.PATCH('/api/v1/comments/{comment_id}', {
          params: { path: { comment_id: command.commentId }, header },
          body: { body: command.body, expected_revision: command.expectedRevision },
        });
      case 'delete':
        return api.DELETE('/api/v1/comments/{comment_id}', {
          params: { path: { comment_id: command.commentId } },
        });
      case 'resolve':
        return api.POST('/api/v1/threads/{thread_id}/resolve', {
          params: { path: { thread_id: command.threadId }, header },
          body: { expected_revision: command.expectedRevision },
        });
      case 'reopen':
        return api.POST('/api/v1/threads/{thread_id}/reopen', {
          params: { path: { thread_id: command.threadId }, header },
          body: { expected_revision: command.expectedRevision },
        });
    }
  })();
  if (result.error) {
    throw toApiError(result.error, result.response);
  }
  return result.data ?? null;
}

/**
 * Every change to a discussion. A command retried after an unknown outcome reuses its key; a
 * different command, or one the API has answered, gets a new key. Success refreshes every list
 * and count of the project's discussions, and its activity log.
 */
export function useDiscussionCommands(projectId: string) {
  const queryClient = useQueryClient();
  const pendingKey = useRef<{ command: string; key: string } | null>(null);
  const mutation = useMutation({
    mutationFn: ({ command, key }: { command: DiscussionCommand; key: string }) =>
      send(projectId, command, key),
    onSuccess: () => {
      pendingKey.current = null;
    },
    onError: (failure) => {
      if (failure instanceof ApiError && !failure.retryable) {
        pendingKey.current = null;
      }
    },
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: discussionsKey(projectId) }),
        queryClient.invalidateQueries({ queryKey: ['activity', projectId] }),
      ]),
  });

  function run(command: DiscussionCommand): Promise<Thread | null> {
    const signature = JSON.stringify(command);
    if (pendingKey.current?.command !== signature) {
      pendingKey.current = { command: signature, key: crypto.randomUUID() };
    }
    return mutation.mutateAsync({ command, key: pendingKey.current.key });
  }

  return { run, isPending: mutation.isPending };
}
