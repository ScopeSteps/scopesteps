import { useCurrentUser } from './useCurrentUser';

/**
 * Names the reviewer behind a user id. Only the signed-in user's name is known to the page;
 * anyone else is described without inventing a name.
 */
export function useReviewerName(): (userId: string | null | undefined) => string {
  const { data: user } = useCurrentUser();
  return (userId) => {
    if (!userId) {
      return 'an unknown reviewer';
    }
    return user?.id === userId ? user.display_name : 'another reviewer';
  };
}
