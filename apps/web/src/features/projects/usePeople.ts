import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { peopleQueryKey } from './people';

/** Everyone the project's sources name, oldest first, as the server reads and corrects them. */
export function usePeople(projectId: string) {
  return useQuery({
    queryKey: peopleQueryKey(projectId),
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/people', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data.people;
    },
  });
}
