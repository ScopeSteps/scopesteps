import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { peopleQueryKey } from './people';
import type { PeopleResponse } from './people';

function usePeopleResponse<T>(projectId: string, select: (data: PeopleResponse) => T) {
  return useQuery({
    queryKey: peopleQueryKey(projectId),
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/projects/{project_id}/people', {
        params: { path: { project_id: projectId } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    select,
  });
}

const selectPeople = (data: PeopleResponse) => data.people;
const selectUnconfirmed = (data: PeopleResponse) => data.unconfirmed_speakers;

/** Everyone on the project, oldest first, as the server reads and corrects them. */
export function usePeople(projectId: string) {
  return usePeopleResponse(projectId, selectPeople);
}

/** The speakers in current transcripts nobody has said who they are yet (ADR 0012). */
export function useUnconfirmedSpeakers(projectId: string) {
  return usePeopleResponse(projectId, selectUnconfirmed);
}
