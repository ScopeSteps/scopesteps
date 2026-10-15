import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { changeRequestQueryKey } from './types';

/** One change request. Disabled until there is one to load. */
export function useChangeRequest(changeRequestId: string | null) {
  return useQuery({
    queryKey: changeRequestQueryKey(changeRequestId),
    enabled: changeRequestId !== null,
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        '/api/v1/change-requests/{change_request_id}',
        { params: { path: { change_request_id: changeRequestId ?? '' } } },
      );
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
