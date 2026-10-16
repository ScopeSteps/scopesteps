import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import { peopleQueryKey } from './people';
import { isStaleSpeakers, speakersQueryKey } from './speakers';
import type { SpeakerAnswer } from './speakers';

interface SentAnswers {
  answers: SpeakerAnswer[];
  expectedRevision: number;
  idempotencyKey: string;
}

/**
 * Saves the whole answer for one transcript in one PUT, at the revision the modal shows. After a
 * save, and after a 409, the people and then the speakers are read again before the caller hears
 * back, so a form rebuilt from them sees new participants and their meeting roles. A 409 is
 * never retried: the modal shows the latest answers and says so.
 */
export function useAssignSpeakers(projectId: string, sourceId: string) {
  const queryClient = useQueryClient();
  async function reload() {
    await queryClient.invalidateQueries({ queryKey: peopleQueryKey(projectId) });
    await queryClient.invalidateQueries({ queryKey: speakersQueryKey(projectId) });
  }
  const mutation = useMutation({
    mutationFn: async ({ answers, expectedRevision, idempotencyKey }: SentAnswers) => {
      const { data, error, response } = await api.PUT(
        '/api/v1/projects/{project_id}/sources/{source_id}/speakers',
        {
          params: {
            path: { project_id: projectId, source_id: sourceId },
            header: { 'Idempotency-Key': idempotencyKey },
          },
          body: { expected_revision: expectedRevision, speakers: answers },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async () => {
      await reload();
      await queryClient.invalidateQueries({ queryKey: ['activity', projectId] });
    },
    onError: async (failure) => {
      if (isStaleSpeakers(failure)) {
        await reload();
      }
    },
  });
  const pendingKey = useRef<{ signature: string; key: string } | null>(null);

  function save(
    answers: SpeakerAnswer[],
    expectedRevision: number,
    callbacks: { onSaved?: () => void; onFailed?: (failure: Error) => void } = {},
  ) {
    if (mutation.isPending) {
      return;
    }
    // The same answers retried after an unknown outcome reuse their key, so they cannot act twice.
    const signature = JSON.stringify({ answers, expectedRevision });
    if (pendingKey.current?.signature !== signature) {
      pendingKey.current = { signature, key: crypto.randomUUID() };
    }
    mutation.mutate(
      { answers, expectedRevision, idempotencyKey: pendingKey.current.key },
      {
        onSuccess: () => {
          pendingKey.current = null;
          callbacks.onSaved?.();
        },
        onError: (failure) => {
          if (failure instanceof ApiError && !failure.retryable) {
            pendingKey.current = null;
          }
          callbacks.onFailed?.(failure);
        },
      },
    );
  }

  return {
    save,
    isPending: mutation.isPending,
    isSuccess: mutation.isSuccess,
    error: mutation.error,
    reset: mutation.reset,
  };
}
