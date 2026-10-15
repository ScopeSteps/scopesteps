import type { components } from '@scopesteps/api-client';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { ApiError, toApiError } from '@/lib/apiError';

import { CURRENT_USER_KEY } from './useCurrentUser';

type UpdateProfileRequest = components['schemas']['UpdateProfileRequest'];

/** The longest name, job title and about text the API accepts, counted after trimming. */
export const PROFILE_LIMITS = { display_name: 60, job_title: 80, about: 280 } as const;

export type ProfileField = keyof typeof PROFILE_LIMITS;

/**
 * Saves the signed-in user's name, job title and about text. The update carries the revision
 * the form was opened on; a stale one is refused with `PROFILE_CHANGED`. Sending the stored
 * profile again succeeds without a new revision, so the API takes no Idempotency-Key here.
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (profile: UpdateProfileRequest) => {
      const { data, error, response } = await api.PATCH('/api/v1/me', { body: profile });
      if (error) {
        throw toApiError(error, response);
      }
      return data;
    },
    onSuccess: async (user) => {
      queryClient.setQueryData(CURRENT_USER_KEY, user);
      // Every project names its members by the profile.
      await queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'identity' && query.queryKey[2] === 'members',
      });
    },
  });
}

/** Someone, perhaps the user in another tab, saved the profile after this form was opened. */
export function isStaleProfile(error: Error | null): boolean {
  return error instanceof ApiError && error.code === 'PROFILE_CHANGED';
}

/** The field the API refused and its reason, or null. */
export function rejectedProfileField(
  error: Error | null,
): { field: ProfileField; message: string } | null {
  if (!(error instanceof ApiError) || error.code !== 'PROFILE_INVALID') {
    return null;
  }
  const field = error.details.field;
  return field === 'display_name' || field === 'job_title' || field === 'about'
    ? { field, message: error.message }
    : null;
}
