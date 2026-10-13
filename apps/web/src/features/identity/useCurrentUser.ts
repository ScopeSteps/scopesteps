import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export function useCurrentUser() {
  return useQuery({
    queryKey: ['identity', 'me'],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/me');
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
