import type { components } from '@scopesteps/api-client';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

import { CURRENT_USER_KEY } from './useCurrentUser';

type SignUpRequest = components['schemas']['SignUpRequest'];

/** Creates an account. The answer is the same whatever the email, so it says only "check it". */
export function useSignUp() {
  return useMutation({
    mutationFn: async (body: SignUpRequest) => {
      const { data, error, response } = await api.POST('/api/v1/auth/sign-up', { body });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}

/** Asks for a new confirmation link. The answer is the same for every address. */
export function useResendVerification() {
  return useMutation({
    mutationFn: async (email: string) => {
      const { data, error, response } = await api.POST('/api/v1/auth/resend-verification', {
        body: { email },
      });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
  });
}

/** Confirms the email a link was sent to; the server starts a session and returns the user. */
export function useVerifyEmail() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (token: string) => {
      const { data, error, response } = await api.POST('/api/v1/auth/verify-email', {
        body: { token },
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
