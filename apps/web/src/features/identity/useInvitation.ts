import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { CURRENT_USER_KEY } from './useCurrentUser';

/** What an invitation link offers: who invited whom to which project, as which roles. */
export function useInvitation(token: string) {
  return useQuery({
    queryKey: ['identity', 'invitation', token],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/invitations/{token}', {
        params: { path: { token } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}

/** Joins the project as the signed-in account the invitation was sent to. */
export function useAcceptInvitation(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error, response } = await api.POST('/api/v1/invitations/{token}/accept', {
        params: { path: { token } },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: (joined) => {
      queryClient.setQueryData(CURRENT_USER_KEY, joined.user);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
    },
  });
}

/** Creates the invited account, joins and signs in, in one step. */
export function useInvitedSignUp(token: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: { display_name: string; password: string }) => {
      const { data, error, response } = await api.POST('/api/v1/invitations/{token}/sign-up', {
        params: { path: { token } },
        body,
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: (joined) => {
      queryClient.setQueryData(CURRENT_USER_KEY, joined.user);
    },
  });
}
