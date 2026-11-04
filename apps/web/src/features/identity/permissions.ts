import type { components } from '@scopesteps/api-client';

import { useCurrentUser } from './useCurrentUser';

type Membership = components['schemas']['MembershipResponse'];
export type Permission = components['schemas']['Permission'];

/**
 * Whether the user's role in the project allows `permission`, as `GET /me` reports it. The API
 * decides what each role allows (ADR 0024) and stays the judge: this only decides which controls
 * to offer.
 */
export function canInProject(
  memberships: readonly Membership[],
  projectId: string,
  permission: Permission,
): boolean {
  return memberships.some(
    (membership) =>
      membership.project_id === projectId && membership.permissions.includes(permission),
  );
}

/** False until `GET /me` has answered, so no control appears before the role is known. */
export function useCan(projectId: string, permission: Permission): boolean {
  const { data: user } = useCurrentUser();
  return user ? canInProject(user.memberships, projectId, permission) : false;
}

/** The user's one role in the project, or null outside it or before `GET /me` answered. */
export function useProjectRole(projectId: string | null): Membership['role'] | null {
  const { data: user } = useCurrentUser();
  return user?.memberships.find((membership) => membership.project_id === projectId)?.role ?? null;
}
