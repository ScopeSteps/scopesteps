import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

/**
 * Runs every approval check on the server for the revision on screen. Review changes nothing,
 * so each run may use a fresh key, and the result is never reused for another revision.
 */
export function useReview(versionId: string, revision: number) {
  return useQuery({
    queryKey: ['backlog', 'review', versionId, revision],
    gcTime: 0,
    queryFn: async () => {
      const { data, error, response } = await api.POST('/api/v1/backlogs/{version_id}/review', {
        params: {
          path: { version_id: versionId },
          header: { 'Idempotency-Key': crypto.randomUUID() },
        },
        body: { expected_revision: revision },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
