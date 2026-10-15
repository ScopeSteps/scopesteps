import type { components } from '@scopesteps/api-client';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { CURRENT_USER_KEY } from './useCurrentUser';

type SignInRequest = components['schemas']['SignInRequest'];

/**
 * Signs in with an email and password. The server sets the session cookie; the page only learns
 * who signed in, and keeps that as the current user.
 */
export function useSignIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: SignInRequest) => {
      const { data, error, response } = await api.POST('/api/v1/auth/sign-in', {
        body: credentials,
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: (user) => {
      queryClient.setQueryData(CURRENT_USER_KEY, user);
    },
  });
}
