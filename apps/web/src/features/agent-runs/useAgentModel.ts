import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

/** The model new runs use. It changes only when the API restarts. */
export function useAgentModel() {
  return useQuery({
    queryKey: ['agent-runs', 'model'],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/agent/model');
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    staleTime: Infinity,
  });
}
