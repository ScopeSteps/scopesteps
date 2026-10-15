import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { changeSetQueryKey } from './types';

/**
 * What a change candidate changes in its baseline, by stable ids, as the server compared them.
 * Disabled until there is a candidate to read; any other version has no change set.
 */
export function useChangeSet(versionId: string | null) {
  return useQuery({
    queryKey: changeSetQueryKey(versionId),
    enabled: versionId !== null,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/backlogs/{version_id}/change-set', {
        params: { path: { version_id: versionId ?? '' } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
