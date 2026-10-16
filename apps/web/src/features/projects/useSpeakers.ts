import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { speakersQueryKey } from './speakers';

/** Every current transcript's speakers, with who they are as far as anyone has said. */
export function useSpeakers(projectId: string) {
  return useQuery({
    queryKey: speakersQueryKey(projectId),
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/speakers', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data.transcripts;
    },
  });
}
