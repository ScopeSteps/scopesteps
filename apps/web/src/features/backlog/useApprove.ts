import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import type { ApprovalDecision, Review } from './types';

/**
 * Approves exactly what the approver reviewed: its revision, content hash and the baseline it
 * builds on (ADR 0008). A retry after an unknown outcome reuses the key, so it cannot approve
 * twice; anything the server answered definitively gets a new key next time.
 */
export function useApprove(projectId: string) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: async ({ review, idempotencyKey }: { review: Review; idempotencyKey: string }) => {
      const { data, error, response } = await api.POST('/api/v1/backlogs/{version_id}/approve', {
        params: {
          path: { version_id: review.version_id },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: {
          expected_revision: review.revision,
          content_hash: review.content_hash,
          expected_baseline_id: review.baseline_version_id,
        },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // A failure changes nothing on the server; the approver reloads and reviews again.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: ['backlog', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
        queryClient.invalidateQueries({ queryKey: ['activity', projectId] }),
        // Approving a candidate also decides its change request (ADR 0011).
        queryClient.invalidateQueries({ queryKey: ['change-control'] }),
      ]),
  });
  const pending = useRef<{ signature: string; key: string } | null>(null);
  const inFlight = useRef(false);

  function approve(review: Review, onApproved: (decision: ApprovalDecision) => void) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    const signature = `${review.version_id}:${String(review.revision)}:${review.content_hash}`;
    if (pending.current?.signature !== signature) {
      pending.current = { signature, key: crypto.randomUUID() };
    }
    mutation.mutate(
      { review, idempotencyKey: pending.current.key },
      {
        onSuccess: (decision) => {
          pending.current = null;
          onApproved(decision);
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

  return { approve, isPending: mutation.isPending, error: mutation.error, reset: mutation.reset };
}
