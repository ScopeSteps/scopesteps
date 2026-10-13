import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { runQueryKey } from './types';

export type RunCommand =
  | { type: 'advance' }
  | { type: 'cancel' }
  | { type: 'answer'; questionId: string; answer: string }
  | { type: 'skip'; questionId: string };

export interface KeyedRunCommand {
  command: RunCommand;
  /** Reuse the same key when retrying the same command, so it cannot act twice. */
  idempotencyKey: string;
}

async function send(runId: string, { command, idempotencyKey }: KeyedRunCommand) {
  const params = {
    path: { run_id: runId },
    header: { 'Idempotency-Key': idempotencyKey },
  };
  switch (command.type) {
    case 'advance':
      return api.POST('/api/v1/runs/{run_id}/advance', { params });
    case 'cancel':
      return api.POST('/api/v1/runs/{run_id}/cancel', { params });
    case 'answer':
      return api.POST('/api/v1/runs/{run_id}/answers', {
        params,
        body: { question_id: command.questionId, answer: command.answer, skip: false },
      });
    case 'skip':
      return api.POST('/api/v1/runs/{run_id}/answers', {
        params,
        body: { question_id: command.questionId, skip: true },
      });
  }
}

/** Sends one command to a run. Every command answers with the run's new state. */
export function useRunCommand(runId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (keyed: KeyedRunCommand) => {
      const { data, error, response } = await send(runId, keyed);
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async (run) => {
      // A read still in flight was answered before this command and must not overwrite it.
      await queryClient.cancelQueries({ queryKey: runQueryKey(runId) });
      queryClient.setQueryData(runQueryKey(runId), run);
    },
    // A 409 means the run is not what this page last saw.
    onError: () => queryClient.invalidateQueries({ queryKey: runQueryKey(runId) }),
  });
}
