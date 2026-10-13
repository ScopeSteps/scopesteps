import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { runQueryKey } from './types';

export interface StartRun {
  sourceVersionIds: string[];
  /** Reuse the same key when retrying, so a retry cannot create a second run. */
  idempotencyKey: string;
}

export function useStartRun(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ sourceVersionIds, idempotencyKey }: StartRun) => {
      const { data, error, response } = await api.POST('/api/v1/projects/{project_id}/runs', {
        params: {
          path: { project_id: projectId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: { mode: 'initial', source_version_ids: sourceVersionIds },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: (run) => {
      queryClient.setQueryData(runQueryKey(run.id), run);
    },
  });
}
