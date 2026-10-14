import type { components } from '@scopesteps/api-client';

import { useCurrentUser } from './useCurrentUser';

type Membership = components['schemas']['MembershipResponse'];
type Role = components['schemas']['Role'];

function holdsRole(memberships: readonly Membership[], projectId: string, role: Role): boolean {
  return memberships.some(
    (membership) => membership.project_id === projectId && membership.role === role,
  );
}

/**
 * Whether the user holds the editor role in the project, which the API asks for to upload
 * sources, start or stop a run, answer its questions and edit a draft. Roles combine and none
 * implies another, so an approver without the editor role cannot edit either. The API stays the
 * judge: this only decides which controls to offer.
 */
export function canEditProject(memberships: readonly Membership[], projectId: string): boolean {
  return holdsRole(memberships, projectId, 'editor');
}

/** Whether the user holds the approver role, which the API asks for to approve a draft. */
export function canApproveProject(memberships: readonly Membership[], projectId: string): boolean {
  return holdsRole(memberships, projectId, 'approver');
}

/** False until `GET /me` has answered, so no control appears before the role is known. */
export function useCanEdit(projectId: string): boolean {
  const { data: user } = useCurrentUser();
  return user ? canEditProject(user.memberships, projectId) : false;
}

/** False until `GET /me` has answered, like `useCanEdit`. */
export function useCanApprove(projectId: string): boolean {
  const { data: user } = useCurrentUser();
  return user ? canApproveProject(user.memberships, projectId) : false;
}
