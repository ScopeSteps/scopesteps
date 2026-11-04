import type { components } from '@scopesteps/api-client';

import type { Permission } from './permissions';

type Role = components['schemas']['Role'];

/**
 * The roles a person can hold in a project, lowest first, with what each allows in plain words.
 * Each role includes everything the one before it can do (ADR 0024).
 */
export const GRANTABLE_ROLES = [
  {
    role: 'viewer',
    label: 'Viewer',
    allows: 'Can read everything and join discussions.',
  },
  {
    role: 'editor',
    label: 'Editor',
    allows: 'Everything a Viewer can do, plus work on sources, the backlog and the chat.',
  },
  {
    role: 'approver',
    label: 'Approver',
    allows: 'Everything an Editor can do, plus approve scope and manage the team.',
  },
] as const satisfies readonly { role: Role; label: string; allows: string }[];

export type GrantableRole = (typeof GRANTABLE_ROLES)[number]['role'];

/** "Viewer", "Editor" or "Approver", as the invite form names it; empty for an admin role. */
export function roleName(role: Role): string {
  return GRANTABLE_ROLES.find((shown) => shown.role === role)?.label ?? '';
}

export function isGrantableRole(role: string): role is GrantableRole {
  return GRANTABLE_ROLES.some((shown) => shown.role === role);
}

// What the rest of the app calls each role (docs/product/glossary.md). The admin roles are not
// shown.
const ROLE_LABELS: Partial<Record<Role, string>> = {
  approver: 'Product owner',
  editor: 'Business analyst',
  viewer: 'Viewer',
};

/** The name the app gives a role, or null for one it does not show (the admin roles). */
export function roleLabelOf(role: Role): string | null {
  return ROLE_LABELS[role] ?? null;
}

const PERMISSION_WORDS: Record<Permission, string> = {
  read: 'Read the backlog, evidence and activity',
  discuss: 'Start and reply to discussions',
  use_agent: 'Chat with the agent and answer its questions',
  manage_sources: 'Add and remove sources',
  edit_backlog: 'Edit drafts and make scope decisions on them',
  manage_people: 'Correct people and decision rights',
  request_changes: 'Ask for changes to the approved backlog',
  moderate_discussions: 'Close anyone’s discussion',
  rename_project: 'Rename the project',
  decide_versions: 'Approve or reject versions',
  manage_members: 'Invite people and change their roles',
};

export interface RolePermissions {
  can: string[];
  cannot: string[];
}

/** The order the permissions are listed in; every permission appears once. */
export const PERMISSION_ORDER: readonly Permission[] = [
  'read',
  'discuss',
  'use_agent',
  'manage_sources',
  'edit_backlog',
  'manage_people',
  'request_changes',
  'moderate_discussions',
  'rename_project',
  'decide_versions',
  'manage_members',
];

/** What a role's permissions allow and do not allow, in plain words and a fixed order. */
export function describePermissions(permissions: readonly Permission[]): RolePermissions {
  return {
    can: PERMISSION_ORDER.filter((p) => permissions.includes(p)).map((p) => PERMISSION_WORDS[p]),
    cannot: PERMISSION_ORDER.filter((p) => !permissions.includes(p)).map(
      (p) => PERMISSION_WORDS[p],
    ),
  };
}
