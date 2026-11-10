import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { versionQueryKey } from '@/features/backlog';
import type { TaskSuggestions } from '@/features/backlog';
import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import { canAdvance, runQueryKey } from './types';
import { useConversation } from './useConversation';
import { useRun } from './useRun';
import { useRunDriver } from './useRunDriver';

interface Started {
  runId: string;
  storyIds: readonly string[] | null;
}

/**
 * Suggests tasks for a draft's stories with the agent: starts a task-suggestion run and, for
 * someone who may edit (`canEdit`), advances it one batch of stories at a time on this page. A
 * run already working when the page opens (started elsewhere) is picked up from the
 * conversation. Each batch is saved on the draft, so the draft is reloaded after every step.
 */
export function useTaskSuggestions(
  projectId: string,
  versionId: string | null,
  canEdit: boolean,
): TaskSuggestions {
  const queryClient = useQueryClient();
  const { activeRun } = useConversation(projectId);
  const [started, setStarted] = useState<Started | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const startKey = useRef<{ signature: string; key: string } | null>(null);
  const runId = started?.runId ?? (activeRun?.mode === 'tasks' ? activeRun.id : null);
  const { data: run } = useRun(runId, { watch: !canEdit });
  const driver = useRunDriver(run, canEdit);

  const start = useMutation({
    mutationFn: async ({ storyIds, key }: { storyIds: readonly string[] | null; key: string }) => {
      const { data, error, response } = await api.POST(
        '/api/v1/projects/{project_id}/backlogs/{version_id}/task-suggestions',
        {
          params: {
            path: { project_id: projectId, version_id: versionId ?? '' },
            header: { 'Idempotency-Key': key },
          },
          body: { story_ids: storyIds === null ? null : [...storyIds] },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: (created, { storyIds }) => {
      startKey.current = null;
      queryClient.setQueryData(runQueryKey(created.id), created);
      setStarted({ runId: created.id, storyIds });
    },
    onError: (failure) => {
      if (failure instanceof ApiError && !failure.retryable) {
        startKey.current = null;
      }
    },
  });

  // Every step saves its batch of suggestions on the draft, so show them as they arrive.
  const revision = run?.revision;
  useEffect(() => {
    if (revision === undefined || versionId === null) {
      return;
    }
    void queryClient.invalidateQueries({ queryKey: versionQueryKey(projectId, versionId) });
  }, [revision, projectId, versionId, queryClient]);

  const shown = run?.mode === 'tasks' && run.id !== dismissed ? run : undefined;
  const working = shown !== undefined && canAdvance(shown) && shown.error === null;
  const runError = shown?.error
    ? new ApiError(0, { ...shown.error, details: {}, request_id: '' })
    : null;

  function suggest(storyIds: readonly string[] | null) {
    if (start.isPending || versionId === null) {
      return;
    }
    // Reused when the same request is retried, so a lost response cannot start a second run.
    const signature = JSON.stringify({ versionId, storyIds });
    if (startKey.current?.signature !== signature) {
      startKey.current = { signature, key: crypto.randomUUID() };
    }
    setDismissed(null);
    start.mutate({ storyIds, key: startKey.current.key });
  }

  return {
    suggest,
    busy: start.isPending || working,
    storyIds: started?.runId === shown?.id ? (started?.storyIds ?? null) : null,
    finished: shown?.status === 'completed',
    error: start.error ?? driver.requestError ?? runError,
    // A refused start is tried again from its button; a failed step from where it stopped.
    retry:
      start.error === null &&
      shown !== undefined &&
      canAdvance(shown) &&
      (driver.requestError !== null || shown.error?.retryable === true)
        ? driver.retry
        : null,
    dismiss: () => {
      start.reset();
      setDismissed(run?.id ?? null);
    },
  };
}
