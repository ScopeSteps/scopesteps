import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { changeRequestsQueryKey, changeSetQueryKey } from '@/features/change-control';
import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import { versionQueryKey } from './types';
import type { BacklogVersion } from './types';

export type ScopeOutcome = 'reverse' | 'keep';

interface SentDecision {
  decisionId: string;
  outcome: ScopeOutcome;
  expectedRevision: number;
  idempotencyKey: string;
}

/**
 * The 409s that mean the candidate on screen is out of date: its revision moved, the decision was
 * answered meanwhile, or the candidate was decided. Reload and look again; never retry.
 */
export function isScopeStale(error: Error | null): error is ApiError {
  return (
    error instanceof ApiError &&
    (error.code === 'VERSION_CHANGED' ||
      error.code === 'DECISION_ALREADY_ANSWERED' ||
      error.code === 'VERSION_NOT_IN_REVIEW')
  );
}

/**
 * An approver's reverse or keep on a candidate's scope decision, at the revision on screen
 * (ADR 0011). The answer is the whole candidate at its next revision, which replaces the cached one.
 */
export function useScopeDecision(projectId: string, version: BacklogVersion) {
  const queryClient = useQueryClient();
  const queryKey = versionQueryKey(projectId, version.id);
  const pendingKey = useRef<{ signature: string; key: string } | null>(null);
  const mutation = useMutation({
    mutationFn: async ({ decisionId, outcome, expectedRevision, idempotencyKey }: SentDecision) => {
      const { data, error, response } = await api.POST(
        '/api/v1/backlogs/{version_id}/scope-decisions/{decision_id}',
        {
          params: {
            path: { version_id: version.id, decision_id: decisionId },
            header: { 'Idempotency-Key': idempotencyKey },
          },
          body: { expected_revision: expectedRevision, outcome },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async (saved) => {
      await queryClient.cancelQueries({ queryKey });
      queryClient.setQueryData(queryKey, saved);
      void queryClient.invalidateQueries({ queryKey: changeSetQueryKey(version.id) });
      void queryClient.invalidateQueries({ queryKey: changeRequestsQueryKey(projectId) });
    },
  });

  function decide(decisionId: string, outcome: ScopeOutcome) {
    if (mutation.isPending) {
      return;
    }
    // The same choice on the same revision reuses its key, so a retry cannot act twice.
    const signature = JSON.stringify({ decisionId, outcome, revision: version.revision });
    if (pendingKey.current?.signature !== signature) {
      pendingKey.current = { signature, key: crypto.randomUUID() };
    }
    mutation.mutate(
      {
        decisionId,
        outcome,
        expectedRevision: version.revision,
        idempotencyKey: pendingKey.current.key,
      },
      {
        onSuccess: () => {
          pendingKey.current = null;
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            pendingKey.current = null;
          }
        },
      },
    );
  }

  async function reload() {
    mutation.reset();
    await queryClient.invalidateQueries({ queryKey });
    await queryClient.invalidateQueries({ queryKey: changeSetQueryKey(version.id) });
  }

  return {
    decide,
    reload,
    isPending: mutation.isPending,
    error: mutation.error,
    outcome: mutation.variables?.outcome ?? null,
  };
}
