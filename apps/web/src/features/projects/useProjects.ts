import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

export const PROJECT_LIST_KEY = ['projects', 'list'] as const;

/** The signed-in user's projects by name, with their roles and scope status. */
export function useProjects() {
  return useQuery({
    queryKey: PROJECT_LIST_KEY,
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects');
      if (error) {
        throw toApiError(error, response);
      }
      return data.projects;
    },
  });
}
