import type { components } from '@scopesteps/api-client';

import { useCurrentUser } from './useCurrentUser';

type Membership = components['schemas']['MembershipResponse'];

/**
 * Whether the user holds the editor role in the project, which the API asks for to upload
 * sources, start or stop a run and answer its questions. Roles combine and none implies
 * another, so an approver without the editor role cannot edit either. The API stays the judge:
 * this only decides which controls to offer.
 */
export function canEditProject(memberships: readonly Membership[], projectId: string): boolean {
  return memberships.some(
    (membership) => membership.project_id === projectId && membership.role === 'editor',
  );
}

/** False until `GET /me` has answered, so no control appears before the role is known. */
export function useCanEdit(projectId: string): boolean {
  const { data: user } = useCurrentUser();
  return user ? canEditProject(user.memberships, projectId) : false;
}
