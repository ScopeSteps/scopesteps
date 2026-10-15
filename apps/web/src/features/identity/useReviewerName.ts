import { useCurrentUser } from './useCurrentUser';
import { useProjectMembers } from './useMemberName';

/**
 * Names the reviewer behind a user id by the display name the server gives them: the signed-in
 * user from `/me`, anyone else from the project's members. Until the members are known, or for
 * someone who no longer has a role in the project, the reviewer is described without inventing
 * a name.
 */
export function useReviewerName(projectId: string): (userId: string | null | undefined) => string {
  const { data: user } = useCurrentUser();
  const { data: members } = useProjectMembers(projectId);
  return (userId) => {
    if (!userId) {
      return 'an unknown reviewer';
    }
    if (user?.id === userId) {
      return user.display_name;
    }
    const member = members?.find((candidate) => candidate.user_id === userId);
    if (member) {
      return member.display_name;
    }
    return members ? 'a former member' : 'a reviewer';
  };
}
