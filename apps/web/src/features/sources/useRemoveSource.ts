import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { sourcesQueryKey } from './useSources';

/**
 * Takes a source out of the project's current sources. The API keeps its versions, so
 * citations to it still resolve, and refuses while anything refers to it (ADR 0009).
 */
export function useRemoveSource(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (sourceId: string) => {
      const { data, error, response } = await api.DELETE(
        '/api/v1/projects/{project_id}/sources/{source_id}',
        {
          params: {
            path: { project_id: projectId, source_id: sourceId },
            // Removal is idempotent by state, so each attempt may use a fresh key.
            header: { 'Idempotency-Key': crypto.randomUUID() },
          },
        },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    // Also after a failure: a refusal can mean the list on screen is out of date. Not awaited:
    // the refreshed list no longer holds the source, which unmounts the viewer's footer, and
    // the caller's success handler must run first.
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: sourcesQueryKey(projectId) });
    },
  });
}
