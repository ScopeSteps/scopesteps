import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import { versionQueryKey } from './types';
import type { BacklogVersion } from './types';

/**
 * An approver keeps flagged personal data on purpose, at the revision on screen. The answer is
 * the whole version, which replaces the cached one, so the approve window's checks run again on
 * the new revision. A 409 is left to the caller: the version changed elsewhere.
 */
export function useKeepPersonalData(projectId: string, version: BacklogVersion) {
  const queryClient = useQueryClient();
  const queryKey = versionQueryKey(projectId, version.id);
  const pending = useRef<{ signature: string; key: string } | null>(null);
  const mutation = useMutation({
    mutationFn: async ({ flagId, key }: { flagId: string; key: string }) => {
      const { data, error, response } = await api.POST(
        '/api/v1/backlogs/{version_id}/personal-data/{flag_id}/keep',
        {
          params: {
            path: { version_id: version.id, flag_id: flagId },
            header: { 'Idempotency-Key': key },
          },
          body: { expected_revision: version.revision },
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
    },
  });

  function keep(flagId: string) {
    if (mutation.isPending) {
      return;
    }
    // Reused when the same keep is retried, so a lost answer cannot record it twice.
    const signature = `${flagId}@${String(version.revision)}`;
    if (pending.current?.signature !== signature) {
      pending.current = { signature, key: crypto.randomUUID() };
    }
    mutation.mutate(
      { flagId, key: pending.current.key },
      {
        onSuccess: () => {
          pending.current = null;
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            pending.current = null;
          }
        },
      },
    );
  }

  return {
    keep,
    keeping: mutation.isPending ? mutation.variables.flagId : null,
    error: mutation.error,
  };
}
