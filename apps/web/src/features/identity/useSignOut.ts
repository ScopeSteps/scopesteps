import { useMutation } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { toApiError } from '@/lib/apiError';

/**
 * Ends the session on the server, then calls `onSignedOut`, which should open sign-in: the
 * sign-in page drops every cached response once the signed-in pages are gone.
 */
export function useSignOut(onSignedOut: () => void) {
  return useMutation({
    mutationFn: async () => {
      const { error, response } = await api.POST('/api/v1/auth/sign-out');
      if (error) {
        throw toApiError(error, response);
      }
    },
    onSuccess: onSignedOut,
  });
}
