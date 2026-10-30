import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { MY_WORK_KEY } from './useMyWork';
import { projectQueryKey } from './useProject';
import { PROJECT_LIST_KEY } from './useProjects';

export interface NewProject {
  name: string;
  /** Reuse the same key when retrying the same name, so a retry cannot create two projects. */
  idempotencyKey: string;
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, idempotencyKey }: NewProject) => {
      const { data, error, response } = await api.POST('/api/v1/projects', {
        params: { header: { 'Idempotency-Key': idempotencyKey } },
        body: { name },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async (project) => {
      queryClient.setQueryData(projectQueryKey(project.id), project);
      // The creator's new roles arrive with `/me` as well as with the list.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: PROJECT_LIST_KEY }),
        queryClient.invalidateQueries({ queryKey: MY_WORK_KEY }),
        queryClient.invalidateQueries({ queryKey: ['identity', 'me'] }),
      ]);
    },
  });
}
