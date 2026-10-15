import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import type { ApprovalDecision, BacklogVersion } from './types';

/**
 * Rejects the version on screen at its revision, with the approver's reason (ADR 0008, ADR 0011).
 * A retry after an unknown outcome reuses the key, so it cannot reject twice; anything the server
 * answered definitively gets a new key next time.
 */
export function useReject(projectId: string) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: async ({
      version,
      reason,
      idempotencyKey,
    }: {
      version: BacklogVersion;
      reason: string;
      idempotencyKey: string;
    }) => {
      const { data, error, response } = await api.POST('/api/v1/backlogs/{version_id}/reject', {
        params: {
          path: { version_id: version.id },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: { expected_revision: version.revision, reason },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['backlog', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
        queryClient.invalidateQueries({ queryKey: ['activity', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['change-control'] }),
      ]),
  });
  const pending = useRef<{ signature: string; key: string } | null>(null);
  const inFlight = useRef(false);

  function reject(
    version: BacklogVersion,
    reason: string,
    onRejected: (decision: ApprovalDecision) => void,
  ) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    const signature = JSON.stringify([version.id, version.revision, reason]);
    if (pending.current?.signature !== signature) {
      pending.current = { signature, key: crypto.randomUUID() };
    }
    mutation.mutate(
      { version, reason, idempotencyKey: pending.current.key },
      {
        onSuccess: (decision) => {
          pending.current = null;
          onRejected(decision);
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            pending.current = null;
          }
        },
        onSettled: () => {
          inFlight.current = false;
        },
      },
    );
  }

  return { reject, isPending: mutation.isPending, error: mutation.error, reset: mutation.reset };
}
