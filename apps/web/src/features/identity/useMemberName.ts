import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

/** Everyone with a role in the project, as the server names them. */
export function useProjectMembers(projectId: string) {
  return useQuery({
    queryKey: ['identity', projectId, 'members'],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/members', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data.members;
    },
  });
}

/**
 * Names a member of the project by user id, or null until the members are known or when the
 * user no longer has a role there. A name is never invented.
 */
export function useMemberName(projectId: string): (userId: string) => string | null {
  const { data: members } = useProjectMembers(projectId);
  return (userId) => members?.find((member) => member.user_id === userId)?.display_name ?? null;
}
