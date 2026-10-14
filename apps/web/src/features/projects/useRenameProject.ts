import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { projectQueryKey } from './useProject';
import { PROJECT_LIST_KEY } from './useProjects';

export interface ProjectRename {
  name: string;
  /** The revision the form was opened on; a stale one is refused with `PROJECT_CHANGED`. */
  expectedRevision: number;
  idempotencyKey: string;
}

export function useRenameProject(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, expectedRevision, idempotencyKey }: ProjectRename) => {
      const { data, error, response } = await api.PATCH('/api/v1/projects/{project_id}', {
        params: {
          path: { project_id: projectId },
          header: { 'Idempotency-Key': idempotencyKey },
        },
        body: { name, expected_revision: expectedRevision },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async (project) => {
      queryClient.setQueryData(projectQueryKey(projectId), project);
      // Exports carry the project's name, and the rename joins the activity log.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: PROJECT_LIST_KEY }),
        queryClient.invalidateQueries({ queryKey: ['backlog', projectId] }),
        queryClient.invalidateQueries({ queryKey: ['activity', projectId] }),
      ]);
    },
  });
}
