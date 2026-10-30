import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export const MY_WORK_KEY = ['projects', 'my-work'] as const;

/** What waits for the signed-in user on each of their projects, most waiting first. */
export function useMyWork() {
  return useQuery({
    queryKey: MY_WORK_KEY,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/me/work');
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}
